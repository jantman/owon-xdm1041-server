"""FastAPI application factory.

Wires the shared Driver and Poller onto the app. When a Database is supplied, the
app's lifespan connects it and runs a Recorder subscribed to the poller's
broadcaster, so live readings are persisted while clients are watching.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ..device.driver import Driver
from ..storage.db import Database
from .api import router
from .poller import Poller
from .recorder import Recorder
from .views import STATIC_DIR, html_router


def create_app(driver: Driver, poller: Poller, database: Database | None = None) -> FastAPI:
    """Build the web application around an existing driver and poller."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        recorder: Recorder | None = None
        if database is not None:
            await database.connect()
            recorder = Recorder(poller.broadcaster, database)
            await recorder.start()
        try:
            yield
        finally:
            if recorder is not None:
                await recorder.stop()
            if database is not None:
                await database.close()

    app = FastAPI(title="OWON XDM1041 Server", lifespan=lifespan)
    app.state.driver = driver
    app.state.poller = poller
    app.state.db = database
    app.include_router(router)
    app.include_router(html_router)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return app
