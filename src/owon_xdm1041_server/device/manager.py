"""The DeviceManager: sole owner and arbiter of the meter connection.

Every component (SCPI server, web poller, manual control) reaches the meter only
through a single DeviceManager. It serialises all access behind a lock so each
command is a single-flight transaction — no interleaved responses on the shared
serial line — and transparently reconnects after a transport failure.

It deliberately keeps the meter in LOCAL mode (``SYST:LOC``) on connect: remote
commands still work, but the physical front panel stays usable, so someone at the
bench is never locked out during a long-running session.
"""

from __future__ import annotations

import asyncio
import contextlib

from . import commands
from .transport import Transport, TransportError


class DeviceError(Exception):
    """Raised when a transaction fails after the transport gave up."""


class DeviceManager:
    """Serialises and supervises access to a single meter transport."""

    def __init__(self, transport: Transport, *, default_timeout: float = 2.0) -> None:
        self._transport = transport
        self._default_timeout = default_timeout
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Open the connection and put the meter in a known state."""
        async with self._lock:
            await self._connect()

    async def stop(self) -> None:
        """Close the connection."""
        async with self._lock:
            await self._transport.close()

    @property
    def is_connected(self) -> bool:
        return self._transport.is_open

    async def query(self, command: str, *, timeout: float | None = None) -> str:
        """Send a command and return its response line."""
        result = await self._transact(command, expect_response=True, timeout=timeout)
        assert result is not None  # expect_response=True always yields a string
        return result

    async def write(self, command: str, *, timeout: float | None = None) -> None:
        """Send a command that produces no response."""
        await self._transact(command, expect_response=False, timeout=timeout)

    async def _connect(self) -> None:
        await self._transport.open()
        # Keep the front panel usable; remote control still works in LOCAL mode.
        await self._transport.transact(
            commands.LOCAL, expect_response=False, timeout=self._default_timeout
        )

    async def _transact(
        self, command: str, *, expect_response: bool, timeout: float | None
    ) -> str | None:
        timeout = self._default_timeout if timeout is None else timeout
        async with self._lock:
            if not self._transport.is_open:
                await self._reconnect()
            try:
                return await self._transport.transact(
                    command, expect_response=expect_response, timeout=timeout
                )
            except TransportError as exc:
                # Drop the connection so the next call reconnects from scratch.
                await self._safe_close()
                raise DeviceError(f"Transaction failed for {command!r}: {exc}") from exc

    async def _reconnect(self) -> None:
        try:
            await self._connect()
        except TransportError as exc:
            await self._safe_close()
            raise DeviceError(f"Reconnect failed: {exc}") from exc

    async def _safe_close(self) -> None:
        with contextlib.suppress(TransportError):  # best-effort cleanup
            await self._transport.close()
