"""Tests for configuration loading."""

from __future__ import annotations

import pytest

from owon_xdm1041_server.config import Settings, load_settings


def test_defaults() -> None:
    s = Settings()
    assert s.baud_rate == 115200
    assert s.scpi_port == 5025
    assert s.serial_port == "/dev/owon-xdm1041"
    assert s.use_mock is False


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OWON_USE_MOCK", "true")
    monkeypatch.setenv("OWON_SCPI_PORT", "6000")
    s = load_settings()
    assert s.use_mock is True
    assert s.scpi_port == 6000


def test_settings_fixture(settings: Settings) -> None:
    assert settings.use_mock is True
    assert settings.database_path.endswith("test.sqlite3")
