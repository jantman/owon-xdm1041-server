"""Tests for the full-server runner."""

from __future__ import annotations

import asyncio

import pytest
import uvicorn

from owon_xdm1041_server import runner
from owon_xdm1041_server.config import Settings


def test_build_components_wires_everything() -> None:
    settings = Settings(use_mock=True, scpi_host="127.0.0.1", scpi_port=5026)  # type: ignore[call-arg]
    components = runner.build_components(settings)
    # The SCPI server and web app share the one manager/driver.
    assert components.scpi._manager is components.manager
    assert components.app.state.driver is components.driver
    assert components.app.state.poller is components.poller
    assert components.app.state.db is components.database


class _FakeServer:
    """A uvicorn.Server stand-in that blocks instead of binding a real socket."""

    def __init__(self, config: uvicorn.Config) -> None:
        self.config = config

    async def serve(self) -> None:
        await asyncio.Event().wait()


async def test_serve_starts_scpi_and_cleans_up_on_cancel() -> None:
    settings = Settings(use_mock=True, scpi_host="127.0.0.1", scpi_port=0, web_port=0)  # type: ignore[call-arg]
    task = asyncio.create_task(runner.serve(settings, server_factory=_FakeServer))
    await asyncio.sleep(0.05)  # let it build and start the SCPI listener
    assert task.done() is False

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
