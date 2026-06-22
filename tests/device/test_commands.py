"""Tests for the SCPI command vocabulary."""

from __future__ import annotations

import pytest

from owon_xdm1041_server.device import commands
from owon_xdm1041_server.device.commands import Function, Rate


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("VOLT", Function.VOLT_DC),
        ("VOLT AC", Function.VOLT_AC),
        ('"VOLT AC"', Function.VOLT_AC),  # meter wraps responses in quotes
        ('"VOLT"', Function.VOLT_DC),
        ("  volt   ac ", Function.VOLT_AC),  # case + whitespace tolerant
        ('  "RES" ', Function.RESISTANCE),  # quotes + surrounding whitespace
        ("RES", Function.RESISTANCE),
        ("TEMP", Function.TEMPERATURE),
    ],
)
def test_function_from_device(raw: str, expected: Function) -> None:
    assert Function.from_device(raw) == expected


def test_function_from_device_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown XDM1041 function"):
        Function.from_device("BOGUS")


def test_rate_from_device() -> None:
    assert Rate.from_device("s") is Rate.SLOW
    assert Rate.from_device("M") is Rate.MEDIUM
    assert Rate.from_device('"F"') is Rate.FAST  # meter wraps responses in quotes
    with pytest.raises(ValueError, match="Unknown XDM1041 rate"):
        Rate.from_device("X")


def test_unit_for() -> None:
    assert commands.unit_for(Function.VOLT_DC) == "V"
    assert commands.unit_for(Function.RESISTANCE) == "Ω"
    assert commands.unit_for(Function.FREQ) == "Hz"


def test_configure_command() -> None:
    assert commands.configure_command(Function.VOLT_AC) == "CONF:VOLT:AC"
    assert commands.configure_command(Function.RESISTANCE) == "CONF:RES"


def test_configure_command_temperature_includes_rtd_type() -> None:
    assert commands.configure_command(Function.TEMPERATURE) == "CONF:TEMP:RTD KITS90"
    assert (
        commands.configure_command(Function.TEMPERATURE, rtd_type="PT100") == "CONF:TEMP:RTD PT100"
    )


def test_set_rate_command() -> None:
    assert commands.set_rate_command(Rate.FAST) == "RATE F"


def test_no_range_query_set() -> None:
    assert Function.DIODE in commands.NO_RANGE_QUERY
    assert Function.CONTINUITY in commands.NO_RANGE_QUERY
    assert Function.VOLT_DC not in commands.NO_RANGE_QUERY
