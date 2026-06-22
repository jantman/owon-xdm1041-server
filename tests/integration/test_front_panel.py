"""Integration test: the server tracks front-panel changes made out of band.

This is the scenario the read-through design exists for. While the server runs,
someone presses the physical buttons (simulated via ``set_front_panel``). Because
the driver re-reads the function on every measurement, the reported value stays
correctly labelled rather than being mislabelled with a stale cached mode.
"""

from __future__ import annotations

from owon_xdm1041_server.device.commands import Function, Rate
from owon_xdm1041_server.device.driver import Driver
from owon_xdm1041_server.device.mock import MockTransport


async def test_measurement_follows_front_panel_change(
    driver: Driver, mock_transport: MockTransport
) -> None:
    # Server starts out seeing DC volts.
    first = await driver.read_measurement()
    assert first.function is Function.VOLT_DC
    assert first.unit == "V"

    # Someone turns the dial to resistance on the physical meter.
    mock_transport.set_front_panel(function=Function.RESISTANCE)

    # The very next reading is correctly re-labelled, no stale cache.
    second = await driver.read_measurement()
    assert second.function is Function.RESISTANCE
    assert second.unit == "Ω"


async def test_state_snapshot_reflects_front_panel_change(
    driver: Driver, mock_transport: MockTransport
) -> None:
    mock_transport.set_front_panel(function=Function.CURR_DC, rate=Rate.SLOW, auto_range=False)
    state = await driver.read_state()
    assert state.function is Function.CURR_DC
    assert state.rate is Rate.SLOW
    assert state.auto_range is False
