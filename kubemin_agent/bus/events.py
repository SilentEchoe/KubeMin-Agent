"""Message bus event types."""

from dataclasses import dataclass, field


@dataclass
class InboundMessage:
    """A message from a channel to the agent."""

    channel: str
    chat_id: str
    content: str
    sender: str = ""
    media: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class OutboundMessage:
    """A message from the agent to a channel."""

    channel: str
    chat_id: str
    content: str
    metadata: dict = field(default_factory=dict)
