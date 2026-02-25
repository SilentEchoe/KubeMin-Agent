"""Base class for chat channels."""

from abc import ABC, abstractmethod

from kubemin_agent.bus.queue import MessageBus


class BaseChannel(ABC):
    """
    Abstract base class for chat channels.

    Channels are responsible for:
    - Connecting to external platforms
    - Authenticating and authorizing users
    - Converting messages between platform and internal formats
    - Publishing inbound messages to the bus
    """

    def __init__(self, bus: MessageBus) -> None:
        self.bus = bus

    @property
    @abstractmethod
    def name(self) -> str:
        """Channel identifier."""
        pass

    @abstractmethod
    async def start(self) -> None:
        """Start the channel and begin receiving messages."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the channel and clean up resources."""
        pass

    @abstractmethod
    async def send_message(self, chat_id: str, content: str) -> None:
        """
        Send a message to a specific chat.

        Args:
            chat_id: Target chat identifier.
            content: Message content.
        """
        pass
