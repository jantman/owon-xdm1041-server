"""Transport layer: the byte pipe to the meter.

Defines the abstract :class:`Transport` interface used by the DeviceManager and a
:class:`SerialTransport` backed by pyserial. Blocking serial I/O is run in a
thread (``asyncio.to_thread``); the DeviceManager serialises access so a single
underlying ``serial.Serial`` is only ever touched by one thread at a time.

The in-memory mock implementation lives in :mod:`.mock`.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

import serial

#: Line terminator the XDM1041 uses for both commands and responses.
TERMINATOR = "\n"


class TransportError(Exception):
    """Raised when the underlying transport fails (I/O error, not open, etc.)."""


class Transport(ABC):
    """Abstract bidirectional connection to the meter."""

    @abstractmethod
    async def open(self) -> None:
        """Open the connection. Idempotent."""

    @abstractmethod
    async def close(self) -> None:
        """Close the connection. Safe to call when already closed."""

    @property
    @abstractmethod
    def is_open(self) -> bool:
        """Whether the connection is currently open."""

    @abstractmethod
    async def transact(self, command: str, *, expect_response: bool, timeout: float) -> str | None:
        """Send ``command`` and optionally read one response line.

        Returns the stripped response string when ``expect_response`` is true,
        otherwise ``None``. Raises :class:`TransportError` on I/O failure or if a
        response is expected but none arrives within ``timeout`` seconds.
        """


class SerialTransport(Transport):
    """A :class:`Transport` over a real serial port via pyserial."""

    def __init__(self, port: str, baud_rate: int) -> None:
        self._port = port
        self._baud_rate = baud_rate
        self._serial: serial.Serial | None = None

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    async def open(self) -> None:
        if self.is_open:
            return
        try:
            # Open with no implicit timeout; transact() sets a per-call timeout.
            self._serial = await asyncio.to_thread(
                serial.Serial,
                self._port,
                self._baud_rate,
                timeout=None,
            )
        except (serial.SerialException, OSError) as exc:
            raise TransportError(f"Failed to open {self._port}: {exc}") from exc

    async def close(self) -> None:
        ser, self._serial = self._serial, None
        if ser is not None and ser.is_open:
            await asyncio.to_thread(ser.close)

    async def transact(self, command: str, *, expect_response: bool, timeout: float) -> str | None:
        if self._serial is None:
            raise TransportError("Transport is not open")
        return await asyncio.to_thread(self._transact_blocking, command, expect_response, timeout)

    def _transact_blocking(self, command: str, expect_response: bool, timeout: float) -> str | None:
        ser = self._serial
        if ser is None:  # pragma: no cover - guarded by transact()
            raise TransportError("Transport is not open")
        try:
            ser.reset_input_buffer()
            ser.write((command + TERMINATOR).encode("ascii"))
            ser.flush()
            if not expect_response:
                return None
            ser.timeout = timeout
            raw = ser.readline()
        except (serial.SerialException, OSError) as exc:
            raise TransportError(f"Serial I/O error on {self._port}: {exc}") from exc
        if not raw:
            raise TransportError(f"No response to {command!r} within {timeout}s")
        return raw.decode("ascii", errors="replace").strip()
