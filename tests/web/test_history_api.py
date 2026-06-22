"""Tests for the history endpoint and end-to-end recording."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from owon_xdm1041_server.config import Settings
from owon_xdm1041_server.device.factory import build_driver
from owon_xdm1041_server.models import Reading
from owon_xdm1041_server.storage.db import Database
from owon_xdm1041_server.web.app import create_app
from owon_xdm1041_server.web.poller import Poller
from owon_xdm1041_server.web.recorder import Recorder


def _client(db_path: str | None) -> TestClient:
    _, driver = build_driver(Settings(use_mock=True))  # type: ignore[call-arg]
    poller = Poller(driver, interval=0.01)
    database = Database(db_path) if db_path is not None else None
    return TestClient(create_app(driver, poller, database))


def _seed(db_path: str) -> None:
    async def run() -> None:
        db = Database(db_path)
        await db.connect()
        await db.insert_reading(Reading(1.0, "VOLT", 1.1, "V"))
        await db.insert_reading(Reading(2.0, "RES", 100.0, "Ω"))
        await db.close()

    asyncio.run(run())


def test_history_returns_seeded_rows(tmp_path: Path) -> None:
    db_path = str(tmp_path / "h.sqlite3")
    _seed(db_path)
    with _client(db_path) as client:
        rows = client.get("/api/history").json()
        assert [r["function"] for r in rows] == ["VOLT", "RES"]  # oldest first


def test_history_function_filter(tmp_path: Path) -> None:
    db_path = str(tmp_path / "h.sqlite3")
    _seed(db_path)
    with _client(db_path) as client:
        rows = client.get("/api/history", params={"function": "RESISTANCE"}).json()
        assert len(rows) == 1
        assert rows[0]["function"] == "RES"


def test_history_since_filter(tmp_path: Path) -> None:
    db_path = str(tmp_path / "h.sqlite3")
    _seed(db_path)
    with _client(db_path) as client:
        rows = client.get("/api/history", params={"since": 1.5}).json()
        assert [r["timestamp"] for r in rows] == [2.0]


def test_history_disabled_without_database() -> None:
    with _client(None) as client:
        assert client.get("/api/history").status_code == 503


async def test_recording_while_watching(tmp_path: Path) -> None:
    db = Database(str(tmp_path / "live.sqlite3"))
    await db.connect()
    _, driver = build_driver(Settings(use_mock=True))  # type: ignore[call-arg]
    poller = Poller(driver, interval=0.005)
    recorder = Recorder(poller.broadcaster, db)
    await recorder.start()

    async with poller.subscribe() as sub:
        for _ in range(3):
            await asyncio.wait_for(anext(sub), 1.0)

    await asyncio.sleep(0.05)  # let the recorder drain
    await recorder.stop()
    assert await db.count() >= 1
    await db.close()
