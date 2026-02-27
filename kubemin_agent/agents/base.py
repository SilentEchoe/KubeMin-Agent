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
        self._trace_task_id = ""
        self._trace_capture_enabled = True
        self._max_trace_steps = 50
        self._trace_events: list[dict[str, Any]] = []
        self._trace_step_index = 0
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
        self._trace_events = []
        self._trace_step_index = 0
        messages: list[dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]
        messages.extend(history[-10:])
        messages.append({"role": "user", "content": message})
        self._record_reasoning_step(
            session_key=session_key,
            phase="plan",
            intent_summary="开始执行任务",
            action="task_start",
            observation_summary=message,
            request_id=request_id,
        )

        for _ in range(self.MAX_ITERATIONS):
            tool_defs = self.tools.get_definitions() if len(self.tools) > 0 else None

            response = await self.provider.chat(
                messages=messages,
                tools=tool_defs,
            )

            if not response.has_tool_calls:
                self._record_reasoning_step(
                    session_key=session_key,
                    phase="synthesis",
                    intent_summary="汇总结果并生成最终回答",
                    action="respond",
                    observation_summary=response.content or "",
                    request_id=request_id,
                )
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
                self._record_reasoning_step(
                    session_key=session_key,
                    phase="tool_call",
                    intent_summary="执行工具调用",
                    action=f"tool:{tc.name}",
                    observation_summary=json.dumps(tc.arguments, ensure_ascii=False),
                    request_id=request_id,
                )
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
                self._record_reasoning_step(
                    session_key=session_key,
                    phase="tool_observation",
                    intent_summary="记录工具执行结果",
                    action=f"tool:{tc.name}",
                    observation_summary=result,
                    error="" if success else result,
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

    def set_trace_context(self, task_id: str = "") -> None:
        """Set per-run trace context from scheduler."""
        self._trace_task_id = task_id

    def set_trace_capture(self, enabled: bool, max_steps: int = 50) -> None:
        """Configure trace capture behavior."""
        self._trace_capture_enabled = enabled
        self._max_trace_steps = max(1, max_steps)

    def consume_trace_events(self) -> list[dict[str, Any]]:
        """Return and clear captured trace events for the latest run."""
        events = list(self._trace_events)
        self._trace_events = []
        return events

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
                task_id=self._trace_task_id,
                request_id=request_id,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to write tool audit log: {e}")

    def _record_reasoning_step(
        self,
        *,
        session_key: str,
        phase: str,
        intent_summary: str,
        action: str,
        observation_summary: str,
        request_id: str,
        confidence: float | None = None,
        error: str = "",
    ) -> None:
        """Capture structured reasoning step and emit audit event when enabled."""
        if not self._trace_capture_enabled:
            return
        if self._trace_step_index >= self._max_trace_steps:
            return

        self._trace_step_index += 1
        event = {
            "step_index": self._trace_step_index,
            "phase": phase,
            "intent_summary": self._preview(intent_summary),
            "action": self._preview(action),
            "observation_summary": self._preview(observation_summary),
            "confidence": confidence,
            "error": self._preview(error),
        }
        self._trace_events.append(event)

        if not self._audit:
            return

        try:
            self._audit.log_reasoning_step(
                session_key=session_key,
                agent_name=self.name,
                task_id=self._trace_task_id,
                step_index=event["step_index"],
                phase=phase,
                intent_summary=event["intent_summary"],
                action=event["action"],
                observation_summary=event["observation_summary"],
                confidence=confidence,
                error=event["error"],
                request_id=request_id,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to write reasoning-step audit log: {e}")

    @staticmethod
    def _preview(value: Any, limit: int = 220) -> str:
        """Convert values into compact text for trace logging."""
        if isinstance(value, str):
            text = value
        else:
            try:
                text = json.dumps(value, ensure_ascii=False)
            except TypeError:
                text = str(value)
        return text[:limit]
