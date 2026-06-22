"""Tests for the raw-socket SCPI server."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from owon_xdm1041_server.device.manager import DeviceManager
from owon_xdm1041_server.device.mock import MockTransport
from owon_xdm1041_server.scpi.server import ScpiServer


@pytest.fixture
async def server(mock_transport: MockTransport) -> AsyncIterator[ScpiServer]:
    manager = DeviceManager(mock_transport)
    await manager.start()
    srv = ScpiServer(manager, host="127.0.0.1", port=0)
    await srv.start()
    yield srv
    await srv.stop()
    await manager.stop()


async def _round_trip(port: int, command: str) -> str:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(command.encode("ascii") + b"\n")
    await writer.drain()
    line = await asyncio.wait_for(reader.readline(), timeout=2.0)
    writer.close()
    await writer.wait_closed()
    return line.decode("ascii").strip()


async def test_query_round_trip(server: ScpiServer) -> None:
    assert await _round_trip(server.port, "*IDN?") == "OWON,XDM1041,MOCK0001,V1.2.0,3"


async def test_write_then_query_over_one_connection(server: ScpiServer) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
    writer.write(b"CONF:RES\n")  # a write: no response expected
    writer.write(b"FUNC1?\n")  # a query: should reflect the write
    await writer.drain()
    line = await asyncio.wait_for(reader.readline(), timeout=2.0)
    # The proxy is transparent: the meter quotes the function name.
    assert line.decode("ascii").strip() == '"RES"'
    writer.close()
    await writer.wait_closed()


async def test_multiple_clients(server: ScpiServer) -> None:
    results = await asyncio.gather(
        _round_trip(server.port, "*IDN?"),
        _round_trip(server.port, "FUNC1?"),
        _round_trip(server.port, "RATE?"),
    )
    assert results[0].startswith("OWON,XDM1041")
    assert results[1] == '"VOLT"'  # transparent proxy: meter quotes the function
    assert results[2] == "M"


async def test_handle_command_empty_is_noop(server: ScpiServer) -> None:
    assert await server.handle_command("   ") is None


async def test_handle_command_write_returns_none(server: ScpiServer) -> None:
    assert await server.handle_command("CONF:RES") is None


async def test_handle_command_swallows_device_error(
    server: ScpiServer, mock_transport: MockTransport
) -> None:
    mock_transport.fail_next()
    # A query that fails returns None rather than raising or crashing the server.
    assert await server.handle_command("*IDN?") is None


async def test_port_before_start_returns_configured() -> None:
    srv = ScpiServer(DeviceManager(MockTransport()), port=5025)
    assert srv.port == 5025


async def test_serve_forever_can_be_cancelled(mock_transport: MockTransport) -> None:
    manager = DeviceManager(mock_transport)
    await manager.start()
    srv = ScpiServer(manager, host="127.0.0.1", port=0)
    task = asyncio.create_task(srv.serve_forever())
    await asyncio.sleep(0.05)  # let it bind and start serving
    assert await _round_trip(srv.port, "*IDN?") != ""
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await srv.stop()
    await manager.stop()
