"""Tests for MessageBus queue bounds and outbound dispatch isolation."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from unittest.mock import patch

import pytest

from kubemin_agent.bus.events import InboundMessage, OutboundMessage
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


@pytest.mark.asyncio
async def test_dispatch_outbound_handles_channel_without_subscribers() -> None:
    bus = MessageBus()
    dispatcher_task = asyncio.create_task(bus.dispatch_outbound())
    await bus.publish_outbound(
        OutboundMessage(channel="missing", chat_id="chat-1", content="noop")
    )
    await asyncio.sleep(0.05)
    assert bus.outbound_size == 0

    bus.stop()
    dispatcher_task.cancel()
    with suppress(asyncio.CancelledError):
        await dispatcher_task


@pytest.mark.asyncio
async def test_dispatch_outbound_loop_handles_timeout_tick() -> None:
    bus = MessageBus()
    task = asyncio.create_task(bus.dispatch_outbound())
    await asyncio.sleep(1.1)
    bus.stop()
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_dispatch_single_subscriber_timeout_and_exception_logged() -> None:
    bus = MessageBus(subscriber_timeout_seconds=0.01)
    msg = OutboundMessage(channel="telegram", chat_id="chat-1", content="hello")

    async def _slow_callback(_msg: OutboundMessage) -> None:
        await asyncio.sleep(0.2)

    async def _raise_callback(_msg: OutboundMessage) -> None:
        raise RuntimeError("boom")

    with patch("kubemin_agent.bus.queue.logger.warning") as warn_log:
        await bus._dispatch_single_subscriber(msg, _slow_callback)
        warn_log.assert_called_once()

    with patch("kubemin_agent.bus.queue.logger.error") as err_log:
        await bus._dispatch_single_subscriber(msg, _raise_callback)
        err_log.assert_called_once()


@pytest.mark.asyncio
async def test_publish_consume_and_queue_size_properties() -> None:
    bus = MessageBus()
    inbound = InboundMessage(channel="cli", chat_id="c1", content="hi")
    outbound = OutboundMessage(channel="cli", chat_id="c1", content="ok")

    await bus.publish_inbound(inbound)
    await bus.publish_outbound(outbound)
    assert bus.inbound_size == 1
    assert bus.outbound_size == 1
    assert await bus.consume_inbound() == inbound
    assert await bus.consume_outbound() == outbound
