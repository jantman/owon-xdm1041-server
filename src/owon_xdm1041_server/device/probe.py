"""A simple connectivity probe: identify the meter and read its state.

Used by the ``probe`` CLI subcommand to confirm the device layer works against
either the mock or a real meter, without any of the server machinery.
"""

from __future__ import annotations

from .driver import Driver


async def run_probe(driver: Driver) -> dict[str, object]:
    """Identify the meter, read a measurement and its state; return a summary."""
    identity = await driver.identify()
    measurement = await driver.read_measurement()
    state = await driver.read_state()
    return {
        "identity": identity,
        "function": state.function.value,
        "rate": state.rate.value,
        "auto_range": state.auto_range,
        "range": state.range,
        "value": measurement.value,
        "unit": measurement.unit,
    }
