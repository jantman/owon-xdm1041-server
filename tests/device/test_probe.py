"""Tests for the device-stack factory, probe routine, and CLI."""

from __future__ import annotations

import pytest

from owon_xdm1041_server import __main__
from owon_xdm1041_server.config import Settings
from owon_xdm1041_server.device.driver import Driver
from owon_xdm1041_server.device.factory import build_driver, build_transport
from owon_xdm1041_server.device.mock import MockTransport
from owon_xdm1041_server.device.probe import run_probe
from owon_xdm1041_server.device.transport import SerialTransport


def test_build_transport_mock() -> None:
    assert isinstance(build_transport(Settings(use_mock=True)), MockTransport)  # type: ignore[call-arg]


def test_build_transport_serial() -> None:
    assert isinstance(build_transport(Settings(use_mock=False)), SerialTransport)  # type: ignore[call-arg]


async def test_run_probe(driver: Driver) -> None:
    summary = await run_probe(driver)
    assert summary["identity"] == "OWON,XDM1041,MOCK0001,V1.2.0,3"
    assert summary["function"] == "VOLT"
    assert summary["unit"] == "V"
    assert summary["range"] == "5V"
    assert isinstance(summary["value"], float)


async def test_build_driver_round_trip() -> None:
    manager, driver = build_driver(Settings(use_mock=True))  # type: ignore[call-arg]
    await manager.start()
    try:
        assert (await driver.identify()).startswith("OWON,XDM1041")
    finally:
        await manager.stop()


def test_cli_probe_mock(capsys: pytest.CaptureFixture[str]) -> None:
    assert __main__.main(["probe", "--mock"]) == 0
    out = capsys.readouterr().out
    assert "OWON,XDM1041,MOCK0001" in out
    assert "function" in out


def test_cli_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert __main__.main([]) == 0
    assert "probe" in capsys.readouterr().out
