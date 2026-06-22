"""A small async pub/sub broadcaster for fanning readings out to live clients.

Each subscriber gets its own bounded queue. If a subscriber falls behind, the
newest reading is dropped for that subscriber rather than blocking the publisher
or growing memory without bound — live data is disposable, so dropping is fine.
"""

from __future__ import annotations

import asyncio
from types import TracebackType

from ..models import Reading


class Subscription:
    """An async-iterable stream of readings for one subscriber."""

    def __init__(self, broadcaster: Broadcaster, maxsize: int = 100) -> None:
        self._broadcaster = broadcaster
        self._queue: asyncio.Queue[Reading] = asyncio.Queue(maxsize)
        self.dropped = 0

    def _deliver(self, reading: Reading) -> None:
        try:
            self._queue.put_nowait(reading)
        except asyncio.QueueFull:
            self.dropped += 1

    async def __aenter__(self) -> Subscription:
        self._broadcaster._register(self)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._broadcaster._unregister(self)

    def __aiter__(self) -> Subscription:
        return self

    async def __anext__(self) -> Reading:
        return await self._queue.get()


class Broadcaster:
    """Fans published readings out to all active subscriptions."""

    def __init__(self) -> None:
        self._subscriptions: set[Subscription] = set()

    @property
    def subscriber_count(self) -> int:
        return len(self._subscriptions)

    def subscribe(self, maxsize: int = 100) -> Subscription:
        """Create a subscription. Use it as an async context manager."""
        return Subscription(self, maxsize=maxsize)

    def _register(self, subscription: Subscription) -> None:
        self._subscriptions.add(subscription)

    def _unregister(self, subscription: Subscription) -> None:
        self._subscriptions.discard(subscription)

    async def publish(self, reading: Reading) -> None:
        for subscription in list(self._subscriptions):
            subscription._deliver(reading)
