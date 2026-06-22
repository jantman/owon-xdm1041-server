"""Tests for the in-memory mock meter."""

from __future__ import annotations

import pytest

from owon_xdm1041_server.device.commands import Function, Rate
from owon_xdm1041_server.device.mock import MockTransport
from owon_xdm1041_server.device.transport import TransportError


async def _q(t: MockTransport, cmd: str) -> str | None:
    return await t.transact(cmd, expect_response=True, timeout=1.0)


@pytest.fixture
async def opened() -> MockTransport:
    t = MockTransport()
    await t.open()
    return t


async def test_open_close_state() -> None:
    t = MockTransport()
    assert t.is_open is False
    await t.open()
    assert t.is_open is True
    await t.close()
    assert t.is_open is False


async def test_transact_when_closed_raises() -> None:
    t = MockTransport()
    with pytest.raises(TransportError, match="not open"):
        await _q(t, "*IDN?")


async def test_identify(opened: MockTransport) -> None:
    assert await _q(opened, "*IDN?") == "OWON,XDM1041,MOCK0001,V1.2.0,3"


async def test_remote_local_tracking(opened: MockTransport) -> None:
    await opened.transact("SYST:REM", expect_response=False, timeout=1.0)
    assert opened.remote is True
    await opened.transact("SYST:LOC", expect_response=False, timeout=1.0)
    assert opened.remote is False


async def test_measure_is_numeric_and_function_dependent(opened: MockTransport) -> None:
    value = float(await _q(opened, "MEAS1?"))  # type: ignore[arg-type]
    assert 3.0 < value < 3.6  # VOLT_DC base 3.3 +/- 1%


async def test_function_and_conf(opened: MockTransport) -> None:
    # Real hardware wraps the function name in literal double-quotes.
    assert await _q(opened, "FUNC1?") == '"VOLT"'
    await opened.transact("CONF:RES", expect_response=False, timeout=1.0)
    assert await _q(opened, "FUNC1?") == '"RES"'
    assert opened.function is Function.RESISTANCE


async def test_conf_volt_ac_beats_volt(opened: MockTransport) -> None:
    await opened.transact("CONF:VOLT:AC AUTO", expect_response=False, timeout=1.0)
    assert opened.function is Function.VOLT_AC
    assert opened.auto_range is True


async def test_rate_query_and_set(opened: MockTransport) -> None:
    assert await _q(opened, "RATE?") == "M"
    await opened.transact("RATE F", expect_response=False, timeout=1.0)
    assert opened.rate is Rate.FAST


async def test_auto_range(opened: MockTransport) -> None:
    assert await _q(opened, "AUTO?") == "1"
    opened.auto_range = False
    assert await _q(opened, "AUTO?") == "0"
    await opened.transact("AUTO", expect_response=False, timeout=1.0)
    assert opened.auto_range is True


async def test_range_query_silent_in_diode(opened: MockTransport) -> None:
    assert await _q(opened, "RANGE?") == "5V"
    opened.set_front_panel(function=Function.DIODE)
    with pytest.raises(TransportError, match="No response"):
        await _q(opened, "RANGE?")


async def test_secondary_function_none(opened: MockTransport) -> None:
    assert await _q(opened, "FUNC2?") == "NONe"
    assert await _q(opened, "MEAS2?") == "NONe"


async def test_write_returns_none(opened: MockTransport) -> None:
    assert await opened.transact("AUTO", expect_response=False, timeout=1.0) is None


async def test_unknown_query_times_out(opened: MockTransport) -> None:
    with pytest.raises(TransportError, match="No response"):
        await _q(opened, "NONSENSE?")


async def test_fail_next(opened: MockTransport) -> None:
    opened.fail_next("boom")
    with pytest.raises(TransportError, match="boom"):
        await _q(opened, "*IDN?")
    # Only the next transaction fails; subsequent ones recover.
    assert await _q(opened, "*IDN?") == "OWON,XDM1041,MOCK0001,V1.2.0,3"


async def test_latency_is_awaited(opened: MockTransport) -> None:
    opened.latency = 0.01
    assert await _q(opened, "*IDN?") is not None


async def test_set_front_panel(opened: MockTransport) -> None:
    opened.set_front_panel(function=Function.RESISTANCE, rate=Rate.SLOW, auto_range=False)
    assert opened.function is Function.RESISTANCE
    assert opened.rate is Rate.SLOW
    assert opened.auto_range is False
