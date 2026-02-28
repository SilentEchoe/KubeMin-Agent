"""Base class for all managed sub-agents."""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from loguru import logger

from kubemin_agent.agent.memory import MemoryStore
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
    DEFAULT_MAX_CONTEXT_TOKENS = 6000
    DEFAULT_MIN_RECENT_HISTORY_MESSAGES = 4
    DEFAULT_TASK_ANCHOR_MAX_CHARS = 600
    DEFAULT_HISTORY_MESSAGE_MAX_CHARS = 1200
    DEFAULT_MEMORY_BACKEND = "file"
    DEFAULT_MEMORY_TOP_K = 5
    DEFAULT_MEMORY_CONTEXT_MAX_CHARS = 1400

    def __init__(
        self,
        provider: LLMProvider,
        sessions: SessionManager,
        audit: Any | None = None,
        workspace: Path | None = None,
        max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
        min_recent_history_messages: int = DEFAULT_MIN_RECENT_HISTORY_MESSAGES,
        task_anchor_max_chars: int = DEFAULT_TASK_ANCHOR_MAX_CHARS,
        history_message_max_chars: int = DEFAULT_HISTORY_MESSAGE_MAX_CHARS,
        memory_backend: str = DEFAULT_MEMORY_BACKEND,
        memory_top_k: int = DEFAULT_MEMORY_TOP_K,
        memory_context_max_chars: int = DEFAULT_MEMORY_CONTEXT_MAX_CHARS,
    ) -> None:
        self.provider = provider
        self.sessions = sessions
        self._audit = audit
        self._workspace = workspace or Path.cwd()
        self._max_context_tokens = max(512, max_context_tokens)
        self._min_recent_history_messages = max(0, min_recent_history_messages)
        self._task_anchor_max_chars = max(120, task_anchor_max_chars)
        self._history_message_max_chars = max(120, history_message_max_chars)
        self._memory_backend = memory_backend
        self._memory_top_k = max(0, memory_top_k)
        self._memory_context_max_chars = max(240, memory_context_max_chars)
        self._trace_task_id = ""
        self._trace_capture_enabled = True
        self._max_trace_steps = 50
        self._trace_events: list[dict[str, Any]] = []
        self._trace_step_index = 0
        self._memory = self._init_memory_store(memory_backend)
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

    async def run(
        self,
        message: str,
        session_key: str,
        request_id: str = "",
        context_envelope: Any | None = None,
    ) -> str:
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
        task_anchor = self._build_task_anchor(message)
        shared_context = self._render_shared_context(context_envelope)
        memory_context = await self._load_memory_context(query=message)
        extra_sections = [section for section in (shared_context, memory_context) if section]
        selected_history = self._select_history_for_budget(
            history=history,
            task_message=message,
            task_anchor=task_anchor,
            extra_sections=extra_sections,
        )

        messages: list[dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]
        messages.append({"role": "system", "content": task_anchor})
        if shared_context:
            messages.append({"role": "system", "content": shared_context})
        if memory_context:
            messages.append({"role": "system", "content": memory_context})
        messages.extend(selected_history)
        messages.append({"role": "user", "content": message})
        self._record_reasoning_step(
            session_key=session_key,
            phase="plan",
            intent_summary="开始执行任务",
            action="task_start",
            observation_summary=(
                f"history_selected={len(selected_history)}, "
                f"history_total={len(history)}, "
                f"context_budget_tokens={self._max_context_tokens}, "
                f"shared_context={'on' if shared_context else 'off'}, "
                f"memory_context={'on' if memory_context else 'off'}"
            ),
            request_id=request_id,
        )

        for _ in range(self.MAX_ITERATIONS):
            tool_defs = self.tools.get_definitions() if len(self.tools) > 0 else None

            response = await self.provider.chat(
                messages=messages + [{"role": "system", "content": self._build_anchor_reminder(message)}],
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

    def _build_task_anchor(self, task_message: str) -> str:
        """Build a stable task anchor to preserve long-running objective focus."""
        objective = self._compact_text(task_message.strip(), self._task_anchor_max_chars)
        return (
            "[TASK ANCHOR]\n"
            "Primary objective:\n"
            f"{objective}\n\n"
            "Execution guardrails:\n"
            "- Keep every step aligned to this objective.\n"
            "- Avoid unrelated exploration.\n"
            "- If conflicts appear, prioritize this objective and safety constraints.\n"
            "- Final response must directly answer this objective."
        )

    def _build_anchor_reminder(self, task_message: str) -> str:
        """Build a compact objective reminder for each reasoning iteration."""
        objective = self._compact_text(task_message.strip(), 220)
        return (
            "[TASK REMINDER]\n"
            f"{objective}\n"
            "Continue only with actions that advance this objective."
        )

    def _select_history_for_budget(
        self,
        *,
        history: list[dict[str, Any]],
        task_message: str,
        task_anchor: str,
        extra_sections: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Select recent history with token budgeting instead of fixed window size."""
        base_tokens = (
            self._estimate_tokens(self.system_prompt)
            + self._estimate_tokens(task_anchor)
            + self._estimate_tokens(task_message)
            + 256
        )
        if extra_sections:
            base_tokens += sum(self._estimate_tokens(section) for section in extra_sections)
        history_budget = max(0, self._max_context_tokens - base_tokens)
        if not history:
            return []

        selected_rev: list[dict[str, Any]] = []
        used_tokens = 0

        for raw in reversed(history):
            role = str(raw.get("role", "user"))
            content = str(raw.get("content", ""))
            if not content.strip():
                continue

            compact = self._compact_text(content, self._history_message_max_chars)
            token_cost = self._estimate_tokens(compact) + 8

            if used_tokens + token_cost > history_budget:
                if len(selected_rev) < self._min_recent_history_messages:
                    remaining_chars = max(120, (history_budget - used_tokens) * 4)
                    clipped = self._compact_text(content, min(remaining_chars, self._history_message_max_chars))
                    selected_rev.append({"role": role, "content": clipped})
                    used_tokens += self._estimate_tokens(clipped) + 8
                    continue
                break

            selected_rev.append({"role": role, "content": compact})
            used_tokens += token_cost

        if not selected_rev:
            last = history[-1]
            return [
                {
                    "role": str(last.get("role", "user")),
                    "content": self._compact_text(str(last.get("content", "")), 240),
                }
            ]

        return list(reversed(selected_rev))

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

    def _init_memory_store(self, backend_type: str) -> MemoryStore | None:
        """Initialize memory store; fallback to file backend if custom backend is unavailable."""
        try:
            return MemoryStore.create(self._workspace, backend_type=backend_type)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"[{self.name}] Failed to init memory backend '{backend_type}': {e}"
            )
            if backend_type == "file":
                return None
            try:
                logger.warning(f"[{self.name}] Falling back to memory backend 'file'")
                return MemoryStore.create(self._workspace, backend_type="file")
            except Exception as inner_e:  # noqa: BLE001
                logger.warning(f"[{self.name}] Failed to init fallback memory backend: {inner_e}")
                return None

    async def _load_memory_context(self, query: str) -> str:
        """Load query-driven memory context for current task message."""
        if not self._memory or self._memory_top_k <= 0:
            return ""

        try:
            memory_context = await self._memory.get_context(query=query, top_k=self._memory_top_k)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[{self.name}] Failed to load memory context: {e}")
            return ""

        if not memory_context.strip():
            return ""

        compact = self._compact_text(memory_context, self._memory_context_max_chars)
        return f"[RELEVANT MEMORY]\n{compact}"

    def _render_shared_context(self, context_envelope: Any | None) -> str:
        """Render scheduler-provided cross-agent context into prompt text."""
        if not context_envelope:
            return ""

        to_prompt = getattr(context_envelope, "to_system_prompt", None)
        if callable(to_prompt):
            try:
                rendered = to_prompt(max_chars=self._history_message_max_chars)
            except TypeError:
                rendered = to_prompt()
            return str(rendered) if rendered else ""

        return self._compact_text(str(context_envelope), self._history_message_max_chars)

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

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Approximate token usage without provider-specific tokenizer dependency."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    def _compact_text(self, text: str, max_chars: int) -> str:
        """Trim long text while preserving visible truncation hints."""
        if len(text) <= max_chars:
            return text
        return f"{text[:max_chars]} ...[truncated {len(text) - max_chars} chars]"
