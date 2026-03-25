"""Tests for MessageBus queue bounds and outbound dispatch isolation."""

from __future__ import annotations

import asyncio
from contextlib import suppress

import pytest

from kubemin_agent.bus.events import OutboundMessage
from kubemin_agent.bus.queue import MessageBus


@pytest.mark.asyncio
async def test_message_bus_uses_bounded_queues() -> None:
    bus = MessageBus(inbound_maxsize=3, outbound_maxsize=4)
    assert bus.inbound.maxsize == 3
    assert bus.outbound.maxsize == 4


@pytest.mark.asyncio
async def test_dispatch_outbound_isolates_slow_subscriber() -> None:
    bus = MessageBus(subscriber_timeout_seconds=0.05)
    fast_done = asyncio.Event()
    slow_started = asyncio.Event()
    slow_finished = asyncio.Event()

    async def fast_callback(_msg: OutboundMessage) -> None:
        fast_done.set()

    async def slow_callback(_msg: OutboundMessage) -> None:
        slow_started.set()
        await asyncio.sleep(1.0)
        slow_finished.set()

    bus.subscribe_outbound("telegram", slow_callback)
    bus.subscribe_outbound("telegram", fast_callback)
    dispatcher_task = asyncio.create_task(bus.dispatch_outbound())
    await bus.publish_outbound(
        OutboundMessage(channel="telegram", chat_id="chat-1", content="hello")
    )

    await asyncio.wait_for(slow_started.wait(), timeout=0.3)
    await asyncio.wait_for(fast_done.wait(), timeout=0.3)
    await asyncio.sleep(0.1)
    assert not slow_finished.is_set()

    bus.stop()
    dispatcher_task.cancel()
    with suppress(asyncio.CancelledError):
        await dispatcher_task
