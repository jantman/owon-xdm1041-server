"""In-memory mock XDM1041.

A stateful fake meter that speaks the SCPI subset the driver uses, so the entire
stack and test suite run with no hardware. Beyond answering commands it exposes
hooks tests rely on:

- :attr:`latency` — simulate a slow meter.
- :meth:`fail_next` — make the next transaction raise, to exercise reconnect.
- :meth:`set_front_panel` — mutate function/rate/range *out of band*, simulating
  someone pressing the physical buttons between remote commands.

Measurement values are deterministic (a function of an internal tick counter), so
tests never depend on randomness.
"""

from __future__ import annotations

import asyncio

from .commands import Function, Rate
from .transport import Transport, TransportError

# A plausible base reading for each function; the mock wobbles this deterministically.
_BASE_VALUES: dict[Function, float] = {
    Function.VOLT_DC: 3.3,
    Function.VOLT_AC: 1.0,
    Function.CURR_DC: 0.05,
    Function.CURR_AC: 0.02,
    Function.FREQ: 1000.0,
    Function.PERIOD: 1.0e-3,
    Function.CAPACITANCE: 1.0e-7,
    Function.CONTINUITY: 12.0,
    Function.DIODE: 0.6,
    Function.RESISTANCE: 1000.0,
    Function.TEMPERATURE: 23.5,
}

# Display string for RANGE? per function (auto mode shown as the default range).
_RANGE_DISPLAY: dict[Function, str] = {
    Function.VOLT_DC: "5V",
    Function.VOLT_AC: "5V",
    Function.CURR_DC: "5A",
    Function.CURR_AC: "5A",
    Function.FREQ: "5V",
    Function.PERIOD: "5V",
    Function.CAPACITANCE: "500nF",
    Function.RESISTANCE: "5KΩ",
}


class MockTransport(Transport):
    """A :class:`Transport` backed by an in-memory meter simulation."""

    def __init__(self) -> None:
        self._open = False
        self.function = Function.VOLT_DC
        self.rate = Rate.MEDIUM
        self.auto_range = True
        self.remote = False
        self.latency = 0.0
        self._tick = 0
        self._fail_next: str | None = None

    # --- test hooks ---
    def fail_next(self, message: str = "simulated transport failure") -> None:
        """Cause the next :meth:`transact` to raise :class:`TransportError`."""
        self._fail_next = message

    def set_front_panel(
        self,
        *,
        function: Function | None = None,
        rate: Rate | None = None,
        auto_range: bool | None = None,
    ) -> None:
        """Mutate meter state as if the physical buttons were used."""
        if function is not None:
            self.function = function
        if rate is not None:
            self.rate = rate
        if auto_range is not None:
            self.auto_range = auto_range

    # --- Transport interface ---
    @property
    def is_open(self) -> bool:
        return self._open

    async def open(self) -> None:
        self._open = True

    async def close(self) -> None:
        self._open = False

    async def transact(self, command: str, *, expect_response: bool, timeout: float) -> str | None:
        if not self._open:
            raise TransportError("Mock transport is not open")
        if self._fail_next is not None:
            message, self._fail_next = self._fail_next, None
            raise TransportError(message)
        if self.latency:
            await asyncio.sleep(self.latency)
        response = self._handle(command.strip())
        if expect_response:
            if response is None:
                raise TransportError(f"No response to {command!r} within {timeout}s")
            return response
        return None

    # --- command interpreter ---
    def _handle(self, command: str) -> str | None:
        upper = command.upper()
        if upper == "*IDN?":
            return "OWON,XDM1041,MOCK0001,V1.2.0,3"
        if upper in ("SYST:REM", "SYST:LOC"):
            self.remote = upper == "SYST:REM"
            return None
        if upper in ("MEAS1?", "MEAS?"):
            return repr(self._measure())
        if upper == "MEAS2?":
            return "NONe"
        if upper in ("FUNC1?", "FUNC?"):
            return self.function.value
        if upper == "FUNC2?":
            return "NONe"
        if upper == "RATE?":
            return self.rate.value
        if upper.startswith("RATE "):
            self.rate = Rate.from_device(command.split()[1])
            return None
        if upper == "AUTO?":
            return "1" if self.auto_range else "0"
        if upper == "AUTO":
            self.auto_range = True
            return None
        if upper == "RANGE?":
            if self.function not in _RANGE_DISPLAY:
                return None  # meter does not answer in DIOD/CONT/TEMP
            return _RANGE_DISPLAY[self.function]
        if upper.startswith("CONF:"):
            self._configure(upper)
            return None
        # Unknown query -> no response (would time out on real hardware).
        return None

    def _configure(self, upper: str) -> None:
        # Longest/most-specific prefixes first so VOLT:AC wins over VOLT.
        mapping = [
            ("CONF:VOLT:AC", Function.VOLT_AC),
            ("CONF:VOLT:DC", Function.VOLT_DC),
            ("CONF:VOLT", Function.VOLT_DC),
            ("CONF:CURR:AC", Function.CURR_AC),
            ("CONF:CURR:DC", Function.CURR_DC),
            ("CONF:CURR", Function.CURR_DC),
            ("CONF:RES", Function.RESISTANCE),
            ("CONF:CAP", Function.CAPACITANCE),
            ("CONF:FREQ", Function.FREQ),
            ("CONF:PER", Function.PERIOD),
            ("CONF:DIOD", Function.DIODE),
            ("CONF:CONT", Function.CONTINUITY),
            ("CONF:TEMP", Function.TEMPERATURE),
        ]
        for prefix, function in mapping:
            if upper.startswith(prefix):
                self.function = function
                if "AUTO" in upper:
                    self.auto_range = True
                return

    def _measure(self) -> float:
        self._tick += 1
        base = _BASE_VALUES[self.function]
        # Deterministic +/-1% wobble derived from the tick counter.
        wobble = ((self._tick % 20) - 10) / 1000.0
        return base * (1.0 + wobble)
