"""Tests for the on-demand poller."""

from __future__ import annotations

import asyncio

from owon_xdm1041_server.device.commands import Function
from owon_xdm1041_server.device.driver import Driver, Measurement
from owon_xdm1041_server.device.manager import DeviceError, DeviceManager
from owon_xdm1041_server.device.mock import MockTransport
from owon_xdm1041_server.web.poller import Poller


def _driver() -> Driver:
    return Driver(DeviceManager(MockTransport()))


async def test_poll_once_returns_and_publishes() -> None:
    poller = Poller(_driver(), interval=0.01, clock=lambda: 42.0)
    async with poller.broadcaster.subscribe() as sub:
        reading = await poller.poll_once()
        assert reading.timestamp == 42.0
        assert reading.unit == "V"
        assert (await asyncio.wait_for(anext(sub), 1.0)).value == reading.value


async def test_poller_is_on_demand() -> None:
    poller = Poller(_driver(), interval=0.01)
    assert poller.is_running is False
    async with poller.subscribe() as sub:
        assert poller.is_running is True
        reading = await asyncio.wait_for(anext(sub), 1.0)
        assert reading.function == "VOLT"
    # Stops once the last subscriber leaves.
    assert poller.is_running is False


async def test_reference_counting_keeps_running_until_last_leaves() -> None:
    poller = Poller(_driver(), interval=0.01)
    async with poller.subscribe():
        async with poller.subscribe():
            assert poller.is_running is True
        # One subscriber remains, so the poller keeps running.
        assert poller.is_running is True
    assert poller.is_running is False


class _FlakyDriver(Driver):
    """Raises DeviceError on the first read, then succeeds."""

    def __init__(self) -> None:
        super().__init__(DeviceManager(MockTransport()))
        self.calls = 0

    async def read_measurement(self) -> Measurement:
        self.calls += 1
        if self.calls == 1:
            raise DeviceError("transient")
        return Measurement(value=1.23, function=Function.VOLT_DC, unit="V")


async def test_poll_loop_survives_device_errors() -> None:
    poller = Poller(_FlakyDriver(), interval=0.001, clock=lambda: 1.0)
    async with poller.subscribe() as sub:
        # Despite the first poll raising, the loop continues and a reading arrives.
        reading = await asyncio.wait_for(anext(sub), 1.0)
        assert reading.value == 1.23
