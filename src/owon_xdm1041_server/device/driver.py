"""High-level driver: meaningful operations on top of raw SCPI transactions.

The driver is deliberately **read-through**: it never trusts a long-lived cache of
the meter's mode. Each measurement re-reads the active function so the returned
value is self-describing and correct even if someone changed the function from the
front panel since the last call (see docs/DESIGN.md, "External state changes").
"""

from __future__ import annotations

from dataclasses import dataclass

from . import commands
from .commands import Function, Rate
from .manager import DeviceError, DeviceManager


@dataclass(frozen=True)
class Measurement:
    """A single reading, tagged with the function in effect when it was taken."""

    value: float
    function: Function
    unit: str


@dataclass(frozen=True)
class DeviceState:
    """A coherent snapshot of the meter's configuration."""

    function: Function
    rate: Rate
    auto_range: bool
    range: str | None


class Driver:
    """Typed, high-level operations over a :class:`DeviceManager`."""

    def __init__(self, manager: DeviceManager) -> None:
        self._manager = manager

    async def identify(self) -> str:
        """Return the meter's ``*IDN?`` identification string."""
        return await self._manager.query(commands.IDENTIFY)

    async def get_function(self) -> Function:
        """Read the active measurement function."""
        return Function.from_device(await self._manager.query(commands.FUNCTION))

    async def set_function(self, function: Function, *, rtd_type: str = "KITS90") -> None:
        """Switch the meter to ``function``."""
        await self._manager.write(commands.configure_command(function, rtd_type=rtd_type))

    async def get_rate(self) -> Rate:
        """Read the measurement rate."""
        return Rate.from_device(await self._manager.query(commands.RATE_QUERY))

    async def set_rate(self, rate: Rate) -> None:
        """Set the measurement rate."""
        await self._manager.write(commands.set_rate_command(rate))

    async def get_auto_range(self) -> bool:
        """Whether auto-range is enabled."""
        return (await self._manager.query(commands.AUTO_RANGE_QUERY)).strip() == "1"

    async def enable_auto_range(self) -> None:
        """Turn auto-range on."""
        await self._manager.write(commands.AUTO_RANGE)

    async def get_range(self, function: Function | None = None) -> str | None:
        """Read the current range display string.

        Returns ``None`` for functions the meter won't answer ``RANGE?`` in
        (DIOD/CONT/TEMP). ``function`` may be supplied to avoid a redundant
        ``FUNC1?`` read when the caller already knows the mode.
        """
        if function is None:
            function = await self.get_function()
        if function in commands.NO_RANGE_QUERY:
            return None
        try:
            return commands._unquote(await self._manager.query(commands.RANGE_QUERY))
        except DeviceError:
            # Some firmware simply stays silent rather than erroring; treat as unknown.
            return None

    async def read_measurement(self) -> Measurement:
        """Take a reading, re-reading the function so the value is self-describing."""
        function = await self.get_function()
        raw = await self._manager.query(commands.MEASURE)
        return Measurement(value=float(raw), function=function, unit=commands.unit_for(function))

    async def read_state(self) -> DeviceState:
        """Read a full, coherent snapshot of the meter's configuration."""
        function = await self.get_function()
        rate = await self.get_rate()
        auto_range = await self.get_auto_range()
        range_ = await self.get_range(function)
        return DeviceState(function=function, rate=rate, auto_range=auto_range, range=range_)
