"""Tests for BaseAgent context budget and task anchor behavior."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from kubemin_agent.agents.base import BaseAgent
from kubemin_agent.providers.base import LLMProvider, LLMResponse
from kubemin_agent.session.manager import SessionManager


class CaptureProvider(LLMProvider):
    """Capture messages passed to the provider for assertions."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[list[dict[str, Any]]] = []

    async def chat(self, messages, tools=None, model=None, max_tokens=4096, temperature=0.7):  # type: ignore[override]
        self.calls.append(messages)
        return LLMResponse(content="ok")

    def get_default_model(self) -> str:
        return "stub"


class DummyAgent(BaseAgent):
    """Minimal concrete agent for context tests."""

    @property
    def name(self) -> str:
        return "dummy"

    @property
    def description(self) -> str:
        return "dummy agent"

    @property
    def system_prompt(self) -> str:
        return "dummy-system-prompt"

    def _register_tools(self) -> None:
        return


def _build_history(sessions: SessionManager, session_key: str, turns: int = 12) -> None:
    for i in range(turns):
        sessions.save_turn(
            session_key,
            f"user-{i} " + ("u" * 180),
            f"assistant-{i} " + ("a" * 180),
        )


@pytest.mark.asyncio
async def test_base_agent_uses_task_anchor_and_budgeted_history(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    session_key = "cli:test_budget"
    sessions = SessionManager(workspace)
    _build_history(sessions, session_key, turns=12)

    provider = CaptureProvider()
    agent = DummyAgent(
        provider=provider,
        sessions=sessions,
        workspace=workspace,
        max_context_tokens=420,
        min_recent_history_messages=2,
        task_anchor_max_chars=80,
        history_message_max_chars=90,
    )

    result = await agent.run("请长流程排查并最终给出结论与建议", session_key=session_key)
    assert result == "ok"
    assert provider.calls

    call_messages = provider.calls[0]
    assert call_messages[0]["role"] == "system"
    assert call_messages[1]["role"] == "system"
    assert "[TASK ANCHOR]" in call_messages[1]["content"]
    assert call_messages[-1]["role"] == "system"
    assert "[TASK REMINDER]" in call_messages[-1]["content"]

    history_slice = call_messages[2:-2]
    assert len(history_slice) < 10
    assert call_messages[-2]["role"] == "user"
    assert "最终给出结论" in call_messages[-2]["content"]


@pytest.mark.asyncio
async def test_base_agent_respects_min_recent_history_when_budget_is_tight(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    session_key = "cli:test_min_recent"
    sessions = SessionManager(workspace)
    _build_history(sessions, session_key, turns=8)

    provider = CaptureProvider()
    agent = DummyAgent(
        provider=provider,
        sessions=sessions,
        workspace=workspace,
        max_context_tokens=360,
        min_recent_history_messages=3,
        task_anchor_max_chars=60,
        history_message_max_chars=70,
    )

    await agent.run("持续执行直到完成目标", session_key=session_key)
    call_messages = provider.calls[0]
    history_slice = call_messages[2:-2]

    assert len(history_slice) >= 3
