"""Base class for all managed sub-agents."""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from pathlib import Path
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
        audit: Any | None = None,
        workspace: Path | None = None,
    ) -> None:
        self.provider = provider
        self.sessions = sessions
        self._audit = audit
        self._workspace = workspace or Path.cwd()
        self.tools = ToolRegistry()
        self._register_tools()
        
        # Enforce allowlist if defined
        if getattr(self, "allowed_tools", None) is not None:
            registered_names = self.tools.tool_names
            for tool_name in registered_names:
                if tool_name not in self.allowed_tools:
                    logger.warning(f"[{self.name}] Removing unauthorized tool '{tool_name}' (not in allowlist)")
                    self.tools.unregister(tool_name)

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

    @property
    def allowed_tools(self) -> list[str]:
        """List of allowed tool names for this agent. Empty list means no tools allowed."""
        return []

    @property
    def allowed_mcps(self) -> list[str]:
        """List of allowed MCP server names for this agent. Empty list means no MCPs allowed."""
        return []

    @abstractmethod
    def _register_tools(self) -> None:
        """Register this agent's domain-specific tools."""
        pass

    async def run(self, message: str, session_key: str, request_id: str = "") -> str:
        """
        Execute the LLM + tool call loop.

        Called by the control plane Scheduler.

        Args:
            message: Task description from the Scheduler.
            session_key: Session identifier.
            request_id: Optional correlation ID for tracing.

        Returns:
            The agent's response.
        """
        history = self.sessions.get_history(session_key)
        messages: list[dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]
        messages.extend(history[-10:])
        messages.append({"role": "user", "content": message})

        for _ in range(self.MAX_ITERATIONS):
            tool_defs = self.tools.get_definitions() if len(self.tools) > 0 else None

            response = await self.provider.chat(
                messages=messages,
                tools=tool_defs,
            )

            if not response.has_tool_calls:
                return response.content or ""

            messages.append(
                {
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
                }
            )

            for tc in response.tool_calls:
                logger.debug(f"[{self.name}] Executing tool: {tc.name}")
                start_time = time.monotonic()
                result = await self.tools.execute(tc.name, tc.arguments)
                duration_ms = (time.monotonic() - start_time) * 1000
                success = not result.startswith("Error")
                self._log_tool_call(
                    session_key=session_key,
                    tool_name=tc.name,
                    params=tc.arguments,
                    result_preview=result,
                    duration_ms=duration_ms,
                    success=success,
                    request_id=request_id,
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": result,
                    }
                )

        return "Reached maximum tool iterations. Please try a simpler request."

    def _log_tool_call(
        self,
        session_key: str,
        tool_name: str,
        params: dict[str, Any],
        result_preview: str,
        duration_ms: float,
        success: bool,
        request_id: str,
    ) -> None:
        """Write tool call trace into audit log when available."""
        if not self._audit:
            return

        try:
            self._audit.log_tool_call(
                session_key=session_key,
                agent_name=self.name,
                tool_name=tool_name,
                params=params,
                result_preview=result_preview,
                duration_ms=duration_ms,
                success=success,
                request_id=request_id,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to write tool audit log: {e}")
