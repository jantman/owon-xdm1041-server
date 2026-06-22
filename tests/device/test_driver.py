"""Tests for the high-level driver."""

from __future__ import annotations

from owon_xdm1041_server.device.commands import Function, Rate
from owon_xdm1041_server.device.driver import Driver
from owon_xdm1041_server.device.mock import MockTransport


async def test_identify(driver: Driver) -> None:
    assert (await driver.identify()).startswith("OWON,XDM1041")


async def test_get_and_set_function(driver: Driver) -> None:
    assert await driver.get_function() is Function.VOLT_DC
    await driver.set_function(Function.RESISTANCE)
    assert await driver.get_function() is Function.RESISTANCE


async def test_get_and_set_rate(driver: Driver) -> None:
    assert await driver.get_rate() is Rate.MEDIUM
    await driver.set_rate(Rate.SLOW)
    assert await driver.get_rate() is Rate.SLOW


async def test_auto_range(driver: Driver, mock_transport: MockTransport) -> None:
    assert await driver.get_auto_range() is True
    mock_transport.auto_range = False
    assert await driver.get_auto_range() is False
    await driver.enable_auto_range()
    assert await driver.get_auto_range() is True


async def test_get_range_reads_active_mode(driver: Driver) -> None:
    # With no hint, get_range reads the live function then queries the range.
    await driver.set_function(Function.RESISTANCE)
    assert await driver.get_range() == "5KΩ"


async def test_get_range_silent_modes_skip_query(driver: Driver) -> None:
    # DIOD/CONT/TEMP are never queried, returning None without hitting the meter.
    assert await driver.get_range(Function.DIODE) is None


async def test_get_range_swallows_device_error(
    driver: Driver, mock_transport: MockTransport
) -> None:
    mock_transport.fail_next()
    assert await driver.get_range(Function.RESISTANCE) is None


async def test_read_measurement_is_self_describing(driver: Driver) -> None:
    m = await driver.read_measurement()
    assert m.function is Function.VOLT_DC
    assert m.unit == "V"
    assert 3.0 < m.value < 3.6


async def test_read_measurement_tracks_function(
    driver: Driver, mock_transport: MockTransport
) -> None:
    await driver.set_function(Function.RESISTANCE)
    m = await driver.read_measurement()
    assert m.function is Function.RESISTANCE
    assert m.unit == "Ω"


async def test_read_state(driver: Driver) -> None:
    state = await driver.read_state()
    assert state.function is Function.VOLT_DC
    assert state.rate is Rate.MEDIUM
    assert state.auto_range is True
    assert state.range == "5V"
