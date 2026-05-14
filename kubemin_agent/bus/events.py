"""Message bus event types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class InboundMessage:
    """A message from a channel to KubeMin-Agent."""

    channel: str
    chat_id: str
    content: str
    sender: str = ""
    media: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def user_id(self) -> str:
        """Canonical user identifier for memory isolation."""
        return self.sender or "local"

    @property
    def tenant_id(self) -> str:
        """Canonical tenant identifier for memory isolation."""
        return str(self.metadata.get("tenant_id") or "default")

    @property
    def team_id(self) -> str:
        """Explicit team identifier for team memory isolation."""
        return str(self.metadata.get("team_id") or "")


@dataclass
class OutboundMessage:
    """A message from KubeMin-Agent back to a channel."""

    channel: str
    chat_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
