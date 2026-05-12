"""Small async message bus."""

from __future__ import annotations

import asyncio

from kubemin_agent.bus.events import InboundMessage, OutboundMessage


class MessageBus:
    """Async queues for inbound and outbound messages."""

    def __init__(self) -> None:
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()

    async def publish_inbound(self, message: InboundMessage) -> None:
        """Publish an inbound message."""
        await self.inbound.put(message)

    async def publish_outbound(self, message: OutboundMessage) -> None:
        """Publish an outbound message."""
        await self.outbound.put(message)
