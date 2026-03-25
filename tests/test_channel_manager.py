"""Tests for ChannelManager message routing and lifecycle handling."""

from __future__ import annotations

import asyncio
from contextlib import suppress

import pytest

from kubemin_agent.bus.events import OutboundMessage
from kubemin_agent.bus.queue import MessageBus
from kubemin_agent.channels.base import BaseChannel
from kubemin_agent.channels.manager import ChannelManager


class DummyChannel(BaseChannel):
    def __init__(self, name: str, bus: MessageBus, fail_start: bool = False, fail_stop: bool = False) -> None:
        super().__init__(bus)
        self._name = name
        self.fail_start = fail_start
        self.fail_stop = fail_stop
        self.started = False
        self.stopped = False
        self.sent_messages: list[tuple[str, str]] = []

    @property
    def name(self) -> str:
        return self._name

    async def start(self) -> None:
        if self.fail_start:
            raise RuntimeError("start failed")
        self.started = True

    async def stop(self) -> None:
        if self.fail_stop:
            raise RuntimeError("stop failed")
        self.stopped = True

    async def send_message(self, chat_id: str, content: str) -> None:
        self.sent_messages.append((chat_id, content))


@pytest.mark.asyncio
async def test_channel_manager_routes_outbound_message() -> None:
    bus = MessageBus()
    manager = ChannelManager(bus)
    channel = DummyChannel("telegram", bus)
    manager.register(channel)

    dispatcher_task = asyncio.create_task(bus.dispatch_outbound())
    await bus.publish_outbound(
        OutboundMessage(channel="telegram", chat_id="chat-1", content="hello")
    )
    await asyncio.sleep(0.05)

    assert manager.channel_names == ["telegram"]
    assert channel.sent_messages == [("chat-1", "hello")]

    bus.stop()
    dispatcher_task.cancel()
    with suppress(asyncio.CancelledError):
        await dispatcher_task


@pytest.mark.asyncio
async def test_channel_manager_start_stop_handles_exceptions() -> None:
    bus = MessageBus()
    manager = ChannelManager(bus)
    good = DummyChannel("good", bus)
    bad_start = DummyChannel("bad-start", bus, fail_start=True)
    bad_stop = DummyChannel("bad-stop", bus, fail_stop=True)

    manager.register(good)
    manager.register(bad_start)
    manager.register(bad_stop)

    await manager.start_all()
    await manager.stop_all()

    assert good.started is True
    assert good.stopped is True
    assert bad_start.started is False
    assert bad_stop.stopped is False
