"""Memory provider extension interface."""

from __future__ import annotations

from abc import ABC
from typing import Any

from kubemin_agent.agent.memory.scope import MemoryScope


class MemoryProvider(ABC):
    """External memory provider lifecycle."""

    name = "provider"

    async def initialize(self) -> None:
        """Connect and prepare provider resources."""

    async def system_prompt_block(self, scope: MemoryScope) -> str:
        """Return static provider context for the prompt."""
        return ""

    async def prefetch(self, scope: MemoryScope, query: str) -> str:
        """Recall query-relevant provider memory before a turn."""
        return ""

    async def sync_turn(
        self,
        scope: MemoryScope,
        user_message: str,
        assistant_response: str,
    ) -> None:
        """Synchronize one completed turn."""

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Return provider-specific tool schemas."""
        return []

    async def handle_tool_call(
        self,
        scope: MemoryScope,
        name: str,
        arguments: dict[str, Any],
    ) -> str:
        """Handle a provider-specific memory tool call."""
        raise KeyError(name)

    async def shutdown(self) -> None:
        """Close provider resources."""


class NoOpMemoryProvider(MemoryProvider):
    """No-op provider used when no external memory backend is configured."""

    name = "none"
