"""Tests for SerialTransport using a fake pyserial backend (no hardware)."""

from __future__ import annotations

import pytest
import serial

from owon_xdm1041_server.device import transport as transport_mod
from owon_xdm1041_server.device.transport import SerialTransport, TransportError


class FakeSerial:
    """Minimal stand-in for ``serial.Serial`` driven by canned response lines."""

    def __init__(
        self,
        port: str,
        baud_rate: int,
        timeout: float | None = None,
        responses: list[bytes] | None = None,
        open_error: bool = False,
        write_error: bool = False,
    ) -> None:
        if open_error:
            raise serial.SerialException("cannot open")
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.is_open = True
        self.written: list[bytes] = []
        self._responses = responses if responses is not None else [b"OK\n"]
        self._write_error = write_error

    def reset_input_buffer(self) -> None:
        return None

    def write(self, data: bytes) -> int:
        if self._write_error:
            raise serial.SerialException("write failed")
        self.written.append(data)
        return len(data)

    def flush(self) -> None:
        return None

    def readline(self) -> bytes:
        return self._responses.pop(0) if self._responses else b""

    def close(self) -> None:
        self.is_open = False


def _install(monkeypatch: pytest.MonkeyPatch, **kwargs: object) -> None:
    def factory(port: str, baud_rate: int, timeout: float | None = None) -> FakeSerial:
        return FakeSerial(port, baud_rate, timeout, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(transport_mod.serial, "Serial", factory)


async def test_open_query_close(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, responses=[b"OWON,XDM1041\n"])
    t = SerialTransport("/dev/ttyUSB0", 115200)
    assert t.is_open is False
    await t.open()
    assert t.is_open is True
    assert await t.transact("*IDN?", expect_response=True, timeout=1.0) == "OWON,XDM1041"
    await t.close()
    assert t.is_open is False


async def test_open_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch)
    t = SerialTransport("/dev/ttyUSB0", 115200)
    await t.open()
    await t.open()  # must not raise or reopen
    assert t.is_open is True


async def test_write_command_appends_terminator(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch)
    t = SerialTransport("/dev/ttyUSB0", 115200)
    await t.open()
    assert await t.transact("CONF:RES", expect_response=False, timeout=1.0) is None
    fake = t._serial  # type: ignore[attr-defined]
    assert fake.written == [b"CONF:RES\n"]


async def test_transact_without_open_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch)
    t = SerialTransport("/dev/ttyUSB0", 115200)
    with pytest.raises(TransportError, match="not open"):
        await t.transact("*IDN?", expect_response=True, timeout=1.0)


async def test_open_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, open_error=True)
    t = SerialTransport("/dev/ttyUSB0", 115200)
    with pytest.raises(TransportError, match="Failed to open"):
        await t.open()


async def test_empty_response_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, responses=[])
    t = SerialTransport("/dev/ttyUSB0", 115200)
    await t.open()
    with pytest.raises(TransportError, match="No response"):
        await t.transact("*IDN?", expect_response=True, timeout=1.0)


async def test_write_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, write_error=True)
    t = SerialTransport("/dev/ttyUSB0", 115200)
    await t.open()
    with pytest.raises(TransportError, match="I/O error"):
        await t.transact("*IDN?", expect_response=True, timeout=1.0)
