"""Raw-socket SCPI server (the de-facto ``TCPIP::host::5025::SOCKET`` interface).

Exposes the meter on the network for tools like pyvisa, NI-VISA, and sigrok. Each
newline-terminated line from a client is forwarded through the DeviceManager, so
the SCPI server, the web UI, and the poller all share one arbitrated connection
to the serial port. Multiple clients may connect at once; the manager serialises
their commands.

Convention: a line containing ``?`` is treated as a query and its response is
written back (newline-terminated); any other line is a write with no reply, which
matches how pyvisa distinguishes ``query`` from ``write``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from ..device.manager import DeviceError, DeviceManager

logger = logging.getLogger(__name__)

TERMINATOR = b"\n"


class ScpiServer:
    """A raw-TCP SCPI passthrough in front of a :class:`DeviceManager`."""

    def __init__(self, manager: DeviceManager, host: str = "0.0.0.0", port: int = 5025) -> None:
        self._manager = manager
        self._host = host
        self._port = port
        self._server: asyncio.Server | None = None

    @property
    def port(self) -> int:
        """The bound port (useful when constructed with port 0 for tests)."""
        if self._server is None:
            return self._port
        return int(self._server.sockets[0].getsockname()[1])

    async def start(self) -> None:
        """Begin listening for connections."""
        self._server = await asyncio.start_server(self._handle_client, self._host, self._port)
        logger.info("SCPI server listening on %s:%d", self._host, self.port)

    async def serve_forever(self) -> None:
        """Serve until cancelled."""
        if self._server is None:
            await self.start()
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> None:
        """Stop listening and wait for the listener to close."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def handle_command(self, command: str) -> str | None:
        """Run one SCPI line, returning the response for a query or ``None``.

        Device errors are logged and swallowed (the client simply receives no
        reply, as with an unresponsive instrument) so one bad command can't take
        the server or other clients down.
        """
        command = command.strip()
        if not command:
            return None
        is_query = "?" in command
        try:
            if is_query:
                return await self._manager.query(command)
            await self._manager.write(command)
            return None
        except DeviceError:
            logger.warning("SCPI command failed: %r", command)
            return None

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        logger.info("SCPI client connected: %s", peer)
        try:
            while True:
                raw = await reader.readline()
                if not raw:  # EOF / disconnect
                    break
                line = raw.decode("ascii", errors="replace")
                response = await self.handle_command(line)
                if response is not None:
                    writer.write(response.encode("ascii") + TERMINATOR)
                    await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):  # pragma: no cover - network race
            pass
        finally:
            logger.info("SCPI client disconnected: %s", peer)
            writer.close()
            with contextlib.suppress(ConnectionError, OSError):  # pragma: no cover
                await writer.wait_closed()
