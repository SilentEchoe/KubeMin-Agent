"""Async message queue for decoupled channel-agent communication."""

import asyncio
from typing import Awaitable, Callable

from loguru import logger

from kubemin_agent.bus.events import InboundMessage, OutboundMessage


class MessageBus:
    """
    Async message bus that decouples chat channels from the agent core.

    Channels push messages to the inbound queue, and the agent processes
    them and pushes responses to the outbound queue.
    """

    def __init__(
        self,
        inbound_maxsize: int = 200,
        outbound_maxsize: int = 200,
        subscriber_timeout_seconds: float = 5.0,
        subscriber_retry_count: int = 0,
        subscriber_retry_backoff_seconds: float = 0.2,
    ) -> None:
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue(
            maxsize=max(1, inbound_maxsize)
        )
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue(
            maxsize=max(1, outbound_maxsize)
        )
        self._outbound_subscribers: dict[
            str, list[Callable[[OutboundMessage], Awaitable[None]]]
        ] = {}
        self._subscriber_timeout_seconds = max(0.1, subscriber_timeout_seconds)
        self._subscriber_retry_count = max(0, subscriber_retry_count)
        self._subscriber_retry_backoff_seconds = max(0.0, subscriber_retry_backoff_seconds)
        self._running = False

    async def publish_inbound(self, msg: InboundMessage) -> None:
        """Publish a message from a channel to the agent."""
        await self.inbound.put(msg)

    async def consume_inbound(self) -> InboundMessage:
        """Consume the next inbound message (blocks until available)."""
        return await self.inbound.get()

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """Publish a response from the agent to channels."""
        await self.outbound.put(msg)

    async def consume_outbound(self) -> OutboundMessage:
        """Consume the next outbound message (blocks until available)."""
        return await self.outbound.get()

    def subscribe_outbound(
        self,
        channel: str,
        callback: Callable[[OutboundMessage], Awaitable[None]],
    ) -> None:
        """Subscribe to outbound messages for a specific channel."""
        if channel not in self._outbound_subscribers:
            self._outbound_subscribers[channel] = []
        self._outbound_subscribers[channel].append(callback)

    async def dispatch_outbound(self) -> None:
        """
        Dispatch outbound messages to subscribed channels.

        Run this as a background task.
        """
        self._running = True
        while self._running:
            try:
                msg = await asyncio.wait_for(self.outbound.get(), timeout=1.0)
                subscribers = self._outbound_subscribers.get(msg.channel, [])
                if not subscribers:
                    continue
                await asyncio.gather(
                    *[self._dispatch_single_subscriber(msg, callback) for callback in subscribers]
                )
            except asyncio.TimeoutError:
                continue

    async def _dispatch_single_subscriber(
        self,
        msg: OutboundMessage,
        callback: Callable[[OutboundMessage], Awaitable[None]],
    ) -> None:
        """Dispatch outbound message to a subscriber with timeout isolation."""
        attempts = self._subscriber_retry_count + 1
        for attempt in range(1, attempts + 1):
            try:
                await asyncio.wait_for(
                    callback(msg),
                    timeout=self._subscriber_timeout_seconds,
                )
                return
            except asyncio.TimeoutError:
                exhausted = attempt == attempts
                logger.warning(
                    "Subscriber timeout while dispatching outbound message: "
                    f"channel={msg.channel}, timeout={self._subscriber_timeout_seconds}s, "
                    f"attempt={attempt}/{attempts}"
                )
                if exhausted:
                    return
            except Exception as e:
                exhausted = attempt == attempts
                logger.error(
                    "Error dispatching outbound message: "
                    f"channel={msg.channel}, attempt={attempt}/{attempts}, error={e}"
                )
                if exhausted:
                    return

            if self._subscriber_retry_backoff_seconds > 0:
                await asyncio.sleep(
                    self._subscriber_retry_backoff_seconds * (2 ** (attempt - 1))
                )

    def stop(self) -> None:
        """Stop the dispatcher loop."""
        self._running = False

    @property
    def inbound_size(self) -> int:
        """Number of pending inbound messages."""
        return self.inbound.qsize()

    @property
    def outbound_size(self) -> int:
        """Number of pending outbound messages."""
        return self.outbound.qsize()
