"""On-demand poller: samples the meter only while clients are watching.

The background polling task starts when the first subscriber arrives and stops
when the last one leaves, so the meter and serial bus stay idle when nobody is
viewing live data (see docs/DESIGN.md). Each sample is published to the
broadcaster for fan-out to WebSocket clients and, later, the recorder.

Polling errors are logged and the loop continues — a transient device hiccup
shouldn't tear down every live client.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from ..device.driver import Driver
from ..device.manager import DeviceError
from ..models import Reading
from .broadcast import Broadcaster, Subscription

logger = logging.getLogger(__name__)


class Poller:
    """Reference-counted background sampler feeding a :class:`Broadcaster`."""

    def __init__(
        self,
        driver: Driver,
        *,
        interval: float = 0.5,
        broadcaster: Broadcaster | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._driver = driver
        self._interval = interval
        self._broadcaster = broadcaster or Broadcaster()
        self._clock = clock
        self._task: asyncio.Task[None] | None = None
        self._subscribers = 0

    @property
    def is_running(self) -> bool:
        return self._task is not None

    @property
    def broadcaster(self) -> Broadcaster:
        return self._broadcaster

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[Subscription]:
        """Subscribe to live readings; starts the poller if it wasn't running."""
        self._subscribers += 1
        self._ensure_running()
        subscription = self._broadcaster.subscribe()
        try:
            async with subscription:
                yield subscription
        finally:
            self._subscribers -= 1
            if self._subscribers == 0:
                await self._stop()

    async def poll_once(self) -> Reading:
        """Take a single reading and publish it. Exposed for tests."""
        measurement = await self._driver.read_measurement()
        reading = Reading.from_measurement(measurement, self._clock())
        await self._broadcaster.publish(reading)
        return reading

    def _ensure_running(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def _stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _loop(self) -> None:
        while True:
            try:
                await self.poll_once()
            except DeviceError:
                logger.warning("Poll failed; continuing", exc_info=True)
            await asyncio.sleep(self._interval)
