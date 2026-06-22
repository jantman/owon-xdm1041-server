"""SCPI command vocabulary for the OWON XDM1041.

Command strings and semantics are taken from the reverse-engineered reference at
https://github.com/TheHWcave/OWON-XDM1041 (SCPI/XDM1041-SCPI.pdf). Notable quirks
encoded here or relied upon elsewhere:

- ``FUNC1?`` returns the active function as a bare string (e.g. ``VOLT AC``).
- ``MEAS1?`` returns the value as an unformatted float with **no unit**, so we
  derive the unit from the function ourselves (the ``*:SHOW?`` variants embed
  non-UTF-8 unit symbols and are avoided).
- ``RANGE?`` is not answered in DIOD/CONT modes.
- ``SYST:REM`` locks the front panel; ``SYST:LOC`` keeps it usable while remote
  commands still work — we keep the device in LOCAL (see DeviceManager).
"""

from __future__ import annotations

from enum import Enum

# --- Common / system commands ---
IDENTIFY = "*IDN?"
REMOTE = "SYST:REM"
LOCAL = "SYST:LOC"

# --- Measurement / state queries ---
MEASURE = "MEAS1?"
FUNCTION = "FUNC1?"
RATE_QUERY = "RATE?"
AUTO_RANGE_QUERY = "AUTO?"
RANGE_QUERY = "RANGE?"

# --- State-changing commands ---
AUTO_RANGE = "AUTO"


class Function(Enum):
    """Measurement functions, keyed by the exact string ``FUNC1?`` returns."""

    VOLT_DC = "VOLT"
    VOLT_AC = "VOLT AC"
    CURR_DC = "CURR"
    CURR_AC = "CURR AC"
    FREQ = "FREQ"
    PERIOD = "PER"
    CAPACITANCE = "CAP"
    CONTINUITY = "CONT"
    DIODE = "DIOD"
    RESISTANCE = "RES"
    TEMPERATURE = "TEMP"

    @classmethod
    def from_device(cls, raw: str) -> Function:
        """Parse a ``FUNC1?`` response into a :class:`Function`.

        Normalises case and internal whitespace so minor formatting differences
        from the meter don't break parsing.
        """
        normalised = " ".join(raw.strip().upper().split())
        for member in cls:
            if member.value == normalised:
                return member
        raise ValueError(f"Unknown XDM1041 function: {raw!r}")


class Rate(Enum):
    """Measurement rate (integration speed)."""

    SLOW = "S"
    MEDIUM = "M"
    FAST = "F"

    @classmethod
    def from_device(cls, raw: str) -> Rate:
        token = raw.strip().upper()
        for member in cls:
            if member.value == token:
                return member
        raise ValueError(f"Unknown XDM1041 rate: {raw!r}")


# SI unit for each function. ``MEAS1?`` is unitless, so we attach this ourselves.
UNITS: dict[Function, str] = {
    Function.VOLT_DC: "V",
    Function.VOLT_AC: "V",
    Function.CURR_DC: "A",
    Function.CURR_AC: "A",
    Function.FREQ: "Hz",
    Function.PERIOD: "s",
    Function.CAPACITANCE: "F",
    Function.CONTINUITY: "Ω",  # Ω
    Function.DIODE: "V",
    Function.RESISTANCE: "Ω",  # Ω
    Function.TEMPERATURE: "°C",  # °C (default; meter unit is configurable)
}

# Base CONFigure command that selects each function. TEMPERATURE needs an RTD
# type argument appended (see :func:`configure_command`).
_CONF_COMMANDS: dict[Function, str] = {
    Function.VOLT_DC: "CONF:VOLT:DC",
    Function.VOLT_AC: "CONF:VOLT:AC",
    Function.CURR_DC: "CONF:CURR:DC",
    Function.CURR_AC: "CONF:CURR:AC",
    Function.RESISTANCE: "CONF:RES",
    Function.CAPACITANCE: "CONF:CAP",
    Function.FREQ: "CONF:FREQ",
    Function.PERIOD: "CONF:PER",
    Function.DIODE: "CONF:DIOD",
    Function.CONTINUITY: "CONF:CONT",
    Function.TEMPERATURE: "CONF:TEMP:RTD",
}

# Functions for which the meter does not answer RANGE?.
NO_RANGE_QUERY: frozenset[Function] = frozenset(
    {Function.DIODE, Function.CONTINUITY, Function.TEMPERATURE}
)


def unit_for(function: Function) -> str:
    """Return the display unit for ``function``."""
    return UNITS[function]


def configure_command(function: Function, *, rtd_type: str = "KITS90") -> str:
    """Build the CONFigure command that switches the meter to ``function``.

    ``rtd_type`` (``KITS90`` for K-type, ``PT100``) is only used for TEMPERATURE.
    """
    base = _CONF_COMMANDS[function]
    if function is Function.TEMPERATURE:
        return f"{base} {rtd_type}"
    return base


def set_rate_command(rate: Rate) -> str:
    """Build the command that sets the measurement rate."""
    return f"RATE {rate.value}"
