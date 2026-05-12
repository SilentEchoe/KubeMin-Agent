"""Base channel contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from kubemin_agent.bus.queue import MessageBus


class BaseChannel(ABC):
    """A channel converts platform messages into internal inbound messages."""

    def __init__(self, bus: MessageBus, tenant_id: str = "default") -> None:
        self.bus = bus
        self.tenant_id = tenant_id or "default"

    @property
    @abstractmethod
    def name(self) -> str:
        """Channel identifier."""

    @abstractmethod
    async def send_message(self, chat_id: str, content: str) -> None:
        """Send a message."""
