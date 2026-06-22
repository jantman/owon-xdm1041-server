"""Tests for the DeviceManager arbiter."""

from __future__ import annotations

import asyncio

import pytest

from owon_xdm1041_server.device.manager import DeviceError, DeviceManager
from owon_xdm1041_server.device.mock import MockTransport
from owon_xdm1041_server.device.transport import Transport, TransportError


async def test_start_puts_meter_in_local_mode() -> None:
    t = MockTransport()
    t.remote = True
    mgr = DeviceManager(t)
    await mgr.start()
    assert mgr.is_connected is True
    assert t.remote is False  # SYST:LOC was issued on connect


async def test_query_and_write(driver_manager: DeviceManager) -> None:
    assert await driver_manager.query("*IDN?") == "OWON,XDM1041,MOCK0001,V1.2.0,3"
    await driver_manager.write("CONF:RES")
    # The manager is a transparent transport: the meter quotes the function name.
    assert await driver_manager.query("FUNC1?") == '"RES"'


async def test_failed_transaction_raises_and_drops_connection() -> None:
    t = MockTransport()
    mgr = DeviceManager(t)
    await mgr.start()
    t.fail_next("io error")
    with pytest.raises(DeviceError, match="Transaction failed"):
        await mgr.query("*IDN?")
    assert mgr.is_connected is False


async def test_auto_reconnect_after_failure() -> None:
    t = MockTransport()
    mgr = DeviceManager(t)
    await mgr.start()
    t.fail_next()
    with pytest.raises(DeviceError):
        await mgr.query("*IDN?")
    # The next call should transparently reconnect and succeed.
    assert await mgr.query("*IDN?") == "OWON,XDM1041,MOCK0001,V1.2.0,3"
    assert mgr.is_connected is True


class _UnopenableTransport(Transport):
    """A transport whose open() always fails, to exercise reconnect failure."""

    @property
    def is_open(self) -> bool:
        return False

    async def open(self) -> None:
        raise TransportError("device missing")

    async def close(self) -> None:
        return None

    async def transact(self, command: str, *, expect_response: bool, timeout: float) -> str | None:
        raise TransportError("never reached")


async def test_reconnect_failure_raises_device_error() -> None:
    mgr = DeviceManager(_UnopenableTransport())
    with pytest.raises(DeviceError, match="Reconnect failed"):
        await mgr.query("*IDN?")


class _ConcurrencyProbe(Transport):
    """Records the maximum number of concurrently in-flight transactions."""

    def __init__(self) -> None:
        self._open = False
        self.active = 0
        self.max_active = 0

    @property
    def is_open(self) -> bool:
        return self._open

    async def open(self) -> None:
        self._open = True

    async def close(self) -> None:
        self._open = False

    async def transact(self, command: str, *, expect_response: bool, timeout: float) -> str | None:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.005)  # widen the window for overlap to show
        finally:
            self.active -= 1
        return "ok" if expect_response else None


async def test_transactions_are_serialised() -> None:
    probe = _ConcurrencyProbe()
    mgr = DeviceManager(probe)
    await mgr.start()
    await asyncio.gather(*(mgr.query("FUNC1?") for _ in range(10)))
    # The lock must prevent interleaved access to the shared serial line.
    assert probe.max_active == 1


@pytest.fixture
async def driver_manager() -> DeviceManager:
    mgr = DeviceManager(MockTransport())
    await mgr.start()
    return mgr
