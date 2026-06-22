"""Compose and run the full server: device stack, SCPI socket, and web UI.

All three interfaces share one DeviceManager, so the serial port has a single
owner regardless of how the meter is being driven. The web app's lifespan owns
the database and recorder; this runner owns the SCPI server and the shared
manager's shutdown.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

import uvicorn
from fastapi import FastAPI

from .config import Settings
from .device.driver import Driver
from .device.factory import build_driver
from .device.manager import DeviceManager
from .scpi.server import ScpiServer
from .storage.db import Database
from .web.app import create_app
from .web.poller import Poller


@dataclass
class Components:
    """The wired-but-not-yet-running pieces of the server."""

    manager: DeviceManager
    driver: Driver
    poller: Poller
    database: Database
    app: FastAPI
    scpi: ScpiServer


def build_components(settings: Settings) -> Components:
    """Construct every component from settings without starting anything."""
    manager, driver = build_driver(settings)
    poller = Poller(driver, interval=settings.poll_interval)
    database = Database(settings.database_path)
    app = create_app(
        driver, poller, database, scpi_host=settings.scpi_host, scpi_port=settings.scpi_port
    )
    scpi = ScpiServer(manager, host=settings.scpi_host, port=settings.scpi_port)
    return Components(
        manager=manager, driver=driver, poller=poller, database=database, app=app, scpi=scpi
    )


async def serve(
    settings: Settings,
    *,
    server_factory: Callable[[uvicorn.Config], uvicorn.Server] = uvicorn.Server,
) -> None:
    """Run the SCPI server and the web UI together until cancelled."""
    components = build_components(settings)
    await components.scpi.start()
    config = uvicorn.Config(
        components.app, host=settings.web_host, port=settings.web_port, log_level="info"
    )
    server = server_factory(config)
    try:
        await asyncio.gather(server.serve(), components.scpi.serve_forever())
    finally:
        await components.scpi.stop()
        await components.manager.stop()
