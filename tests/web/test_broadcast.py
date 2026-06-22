"""Tests for the pub/sub broadcaster."""

from __future__ import annotations

import asyncio

from owon_xdm1041_server.models import Reading
from owon_xdm1041_server.web.broadcast import Broadcaster


def _reading(value: float) -> Reading:
    return Reading(timestamp=1.0, function="VOLT", value=value, unit="V")


async def test_subscribe_registers_and_unregisters() -> None:
    b = Broadcaster()
    assert b.subscriber_count == 0
    async with b.subscribe():
        assert b.subscriber_count == 1
    assert b.subscriber_count == 0


async def test_publish_delivers_to_subscriber() -> None:
    b = Broadcaster()
    async with b.subscribe() as sub:
        await b.publish(_reading(1.5))
        reading = await asyncio.wait_for(anext(sub), 1.0)
        assert reading.value == 1.5


async def test_publish_fans_out_to_all() -> None:
    b = Broadcaster()
    async with b.subscribe() as a, b.subscribe() as c:
        await b.publish(_reading(2.0))
        assert (await asyncio.wait_for(anext(a), 1.0)).value == 2.0
        assert (await asyncio.wait_for(anext(c), 1.0)).value == 2.0


async def test_slow_subscriber_drops_instead_of_blocking() -> None:
    b = Broadcaster()
    async with b.subscribe(maxsize=1) as sub:
        await b.publish(_reading(1.0))
        await b.publish(_reading(2.0))  # dropped: queue full
        await b.publish(_reading(3.0))  # dropped: queue full
        assert sub.dropped == 2
        assert (await asyncio.wait_for(anext(sub), 1.0)).value == 1.0


async def test_publish_with_no_subscribers_is_noop() -> None:
    b = Broadcaster()
    await b.publish(_reading(1.0))  # must not raise
    assert b.subscriber_count == 0
