"""MemoryEntry data model for structured memory storage."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class MemoryEntry:
    """
    A single unit of agent memory.

    Attributes:
        id: Unique identifier.
        content: The memory content text.
        tags: Tags for filtering and categorization.
        created_at: When the memory was created.
        source: Origin of the memory (agent name, session key, etc.).
        metadata: Arbitrary extension fields.
    """

    id: str
    content: str
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "id": self.id,
            "content": self.content,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "source": self.source,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryEntry:
        """Deserialize from a dict."""
        return cls(
            id=data["id"],
            content=data["content"],
            tags=data.get("tags", []),
            created_at=datetime.fromisoformat(data["created_at"]),
            source=data.get("source", ""),
            metadata=data.get("metadata", {}),
        )
