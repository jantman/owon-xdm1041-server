"""Recorder: persists broadcast readings to the database.

It subscribes to the broadcaster *directly* rather than through the poller, so it
records whatever readings flow but does not itself count as a viewer. This keeps
polling on-demand: when nobody is watching, the poller is idle and nothing is
recorded — the documented tradeoff in docs/DESIGN.md.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from ..storage.db import Database
from .broadcast import Broadcaster

logger = logging.getLogger(__name__)


class Recorder:
    """Writes every broadcast reading to the database while running."""

    def __init__(self, broadcaster: Broadcaster, database: Database) -> None:
        self._broadcaster = broadcaster
        self._database = database
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _run(self) -> None:
        async with self._broadcaster.subscribe() as subscription:
            async for reading in subscription:
                try:
                    await self._database.insert_reading(reading)
                except Exception:
                    logger.warning("Failed to persist reading", exc_info=True)
