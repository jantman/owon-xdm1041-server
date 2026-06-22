"""Shared pytest fixtures.

Everything here is hardware-free: the device fixtures are wired to the in-memory
:class:`MockTransport`, so the whole suite runs without a meter attached.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from owon_xdm1041_server.config import Settings
from owon_xdm1041_server.device.driver import Driver
from owon_xdm1041_server.device.manager import DeviceManager
from owon_xdm1041_server.device.mock import MockTransport


@pytest.fixture
def settings(tmp_path: object) -> Settings:
    """A Settings instance wired for hardware-free testing against the mock meter."""
    return Settings(use_mock=True, database_path=str(tmp_path) + "/test.sqlite3")  # type: ignore[call-arg]


@pytest.fixture
def mock_transport() -> MockTransport:
    return MockTransport()


@pytest.fixture
async def manager(mock_transport: MockTransport) -> AsyncIterator[DeviceManager]:
    mgr = DeviceManager(mock_transport, default_timeout=1.0)
    await mgr.start()
    yield mgr
    await mgr.stop()


@pytest.fixture
def driver(manager: DeviceManager) -> Driver:
    return Driver(manager)
