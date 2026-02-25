"""Base class for all managed sub-agents."""

import json
from abc import ABC, abstractmethod
from typing import Any

from loguru import logger

from kubemin_agent.agent.tools.registry import ToolRegistry
from kubemin_agent.providers.base import LLMProvider
from kubemin_agent.session.manager import SessionManager


class BaseAgent(ABC):
    """
    Abstract base class for sub-agents.

    Sub-agents are managed by the control plane's Scheduler.
    Each has its own system prompt, tool set, and domain expertise.
    """

    MAX_ITERATIONS = 20

    def __init__(
        self,
        provider: LLMProvider,
        sessions: SessionManager,
    ) -> None:
        self.provider = provider
        self.sessions = sessions
        self.tools = ToolRegistry()
        self._register_tools()

    @property
    @abstractmethod
    def name(self) -> str:
        """Sub-agent identifier."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Capability description (used by Scheduler for routing)."""
        pass

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Domain-specific system prompt."""
        pass

    @abstractmethod
    def _register_tools(self) -> None:
        """Register this agent's domain-specific tools."""
        pass

    async def run(self, message: str, session_key: str) -> str:
        """
        Execute the LLM + tool call loop.

        Called by the control plane Scheduler.

        Args:
            message: Task description from the Scheduler.
            session_key: Session identifier.

        Returns:
            The agent's response.
        """
        # Build messages
        history = self.sessions.get_history(session_key)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
        ]
        messages.extend(history[-10:])  # Include recent context
        messages.append({"role": "user", "content": message})

        # Tool call loop
        for iteration in range(self.MAX_ITERATIONS):
            tool_defs = self.tools.get_definitions() if len(self.tools) > 0 else None

            response = await self.provider.chat(
                messages=messages,
                tools=tool_defs,
            )

            if not response.has_tool_calls:
                return response.content or ""

            # Add assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in response.tool_calls
                ],
            })

            # Execute tool calls
            for tc in response.tool_calls:
                logger.debug(f"[{self.name}] Executing tool: {tc.name}")
                result = await self.tools.execute(tc.name, tc.arguments)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "content": result,
                })

        return "Reached maximum tool iterations. Please try a simpler request."
