"""Tests for the recorder."""

from __future__ import annotations

import asyncio
from pathlib import Path

from owon_xdm1041_server.models import Reading
from owon_xdm1041_server.storage.db import Database
from owon_xdm1041_server.web.broadcast import Broadcaster
from owon_xdm1041_server.web.recorder import Recorder


async def _wait_for_subscriber(broadcaster: Broadcaster) -> None:
    for _ in range(100):
        if broadcaster.subscriber_count > 0:
            return
        await asyncio.sleep(0.001)


async def test_recorder_persists_published_readings(tmp_path: Path) -> None:
    db = Database(str(tmp_path / "rec.sqlite3"))
    await db.connect()
    broadcaster = Broadcaster()
    recorder = Recorder(broadcaster, db)
    await recorder.start()
    await _wait_for_subscriber(broadcaster)

    await broadcaster.publish(Reading(1.0, "VOLT", 3.3, "V"))
    for _ in range(100):
        if await db.count() == 1:
            break
        await asyncio.sleep(0.001)
    assert await db.count() == 1

    await recorder.stop()
    await db.close()


async def test_start_and_stop_are_idempotent(tmp_path: Path) -> None:
    db = Database(str(tmp_path / "rec.sqlite3"))
    await db.connect()
    recorder = Recorder(Broadcaster(), db)
    assert recorder.is_running is False
    await recorder.start()
    await recorder.start()  # no-op
    assert recorder.is_running is True
    await recorder.stop()
    await recorder.stop()  # no-op
    assert recorder.is_running is False
    await db.close()


class _BoomDatabase(Database):
    async def insert_reading(self, reading: Reading) -> None:
        raise RuntimeError("disk on fire")


async def test_recorder_survives_write_errors() -> None:
    broadcaster = Broadcaster()
    recorder = Recorder(broadcaster, _BoomDatabase(":memory:"))
    await recorder.start()
    await _wait_for_subscriber(broadcaster)
    await broadcaster.publish(Reading(1.0, "VOLT", 1.0, "V"))
    await asyncio.sleep(0.02)
    # The failing write is logged and swallowed; the recorder keeps running.
    assert recorder.is_running is True
    await recorder.stop()
