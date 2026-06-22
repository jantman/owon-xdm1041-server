"""FastAPI application factory.

Wires the shared Driver and Poller onto the app so the API routes can reach them.
HTML pages and static assets are added in a later phase.
"""

from __future__ import annotations

from fastapi import FastAPI

from ..device.driver import Driver
from .api import router
from .poller import Poller


def create_app(driver: Driver, poller: Poller) -> FastAPI:
    """Build the web application around an existing driver and poller."""
    app = FastAPI(title="OWON XDM1041 Server")
    app.state.driver = driver
    app.state.poller = poller
    app.include_router(router)
    return app
