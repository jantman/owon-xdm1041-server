"""Tests for the SQLite storage layer."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from owon_xdm1041_server.models import Reading
from owon_xdm1041_server.storage.db import Database


@pytest.fixture
async def db(tmp_path: Path) -> AsyncIterator[Database]:
    database = Database(str(tmp_path / "readings.sqlite3"))
    await database.connect()
    yield database
    await database.close()


def _r(ts: float, function: str = "VOLT", value: float = 1.0, unit: str = "V") -> Reading:
    return Reading(timestamp=ts, function=function, value=value, unit=unit)


async def test_insert_and_count(db: Database) -> None:
    assert await db.count() == 0
    await db.insert_reading(_r(1.0))
    await db.insert_reading(_r(2.0))
    assert await db.count() == 2


async def test_history_orders_oldest_first(db: Database) -> None:
    await db.insert_reading(_r(3.0, value=3.0))
    await db.insert_reading(_r(1.0, value=1.0))
    await db.insert_reading(_r(2.0, value=2.0))
    values = [r.value for r in await db.history()]
    assert values == [1.0, 2.0, 3.0]


async def test_history_time_filters(db: Database) -> None:
    for ts in (1.0, 2.0, 3.0, 4.0):
        await db.insert_reading(_r(ts))
    assert [r.timestamp for r in await db.history(since=2.0)] == [2.0, 3.0, 4.0]
    assert [r.timestamp for r in await db.history(until=2.0)] == [1.0, 2.0]
    assert [r.timestamp for r in await db.history(since=2.0, until=3.0)] == [2.0, 3.0]


async def test_history_function_filter(db: Database) -> None:
    await db.insert_reading(_r(1.0, function="VOLT"))
    await db.insert_reading(_r(2.0, function="RES", unit="Ω"))
    rows = await db.history(function="RES")
    assert len(rows) == 1
    assert rows[0].function == "RES"
    assert rows[0].unit == "Ω"


async def test_history_limit_keeps_most_recent(db: Database) -> None:
    for ts in range(1, 11):
        await db.insert_reading(_r(float(ts)))
    rows = await db.history(limit=3)
    # Most recent three, presented oldest-first.
    assert [r.timestamp for r in rows] == [8.0, 9.0, 10.0]


async def test_operations_require_connection(tmp_path: Path) -> None:
    database = Database(str(tmp_path / "x.sqlite3"))
    with pytest.raises(RuntimeError, match="not connected"):
        await database.count()
