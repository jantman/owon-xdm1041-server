"""SQLite persistence for recorded readings (async, via aiosqlite).

Readings are stored append-only, each tagged with the function actually in effect
when it was taken, so history stays correctly attributed across front-panel mode
changes. The schema is intentionally tiny; downsampling for charts is done at
query time.
"""

from __future__ import annotations

import aiosqlite

from ..models import Reading

_SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       REAL NOT NULL,
    function TEXT NOT NULL,
    value    REAL NOT NULL,
    unit     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_readings_ts ON readings (ts);
"""


class Database:
    """An async SQLite store for :class:`Reading` rows."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Open the database and ensure the schema exists."""
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def _db(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        return self._conn

    async def insert_reading(self, reading: Reading) -> None:
        """Append a single reading."""
        await self._db.execute(
            "INSERT INTO readings (ts, function, value, unit) VALUES (?, ?, ?, ?)",
            (reading.timestamp, reading.function, reading.value, reading.unit),
        )
        await self._db.commit()

    async def history(
        self,
        *,
        since: float | None = None,
        until: float | None = None,
        function: str | None = None,
        limit: int = 1000,
    ) -> list[Reading]:
        """Return readings matching the filters, oldest first.

        ``function`` is matched against the stored device string (e.g. ``VOLT``).
        """
        clauses: list[str] = []
        params: list[object] = []
        if since is not None:
            clauses.append("ts >= ?")
            params.append(since)
        if until is not None:
            clauses.append("ts <= ?")
            params.append(until)
        if function is not None:
            clauses.append("function = ?")
            params.append(function)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        # Take the most recent `limit` rows, then present them oldest-first.
        query = f"SELECT ts, function, value, unit FROM readings {where} ORDER BY ts DESC LIMIT ?"
        params.append(limit)
        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        readings = [
            Reading(
                timestamp=row["ts"], function=row["function"], value=row["value"], unit=row["unit"]
            )
            for row in rows
        ]
        readings.reverse()
        return readings

    async def count(self) -> int:
        """Total number of stored readings."""
        async with self._db.execute("SELECT COUNT(*) AS n FROM readings") as cursor:
            row = await cursor.fetchone()
        return int(row["n"]) if row is not None else 0
