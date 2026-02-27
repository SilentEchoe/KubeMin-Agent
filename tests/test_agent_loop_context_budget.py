"""Tests for AgentLoop context budgeting and task anchor behavior."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from kubemin_agent.agent.loop import AgentLoop
from kubemin_agent.bus.queue import MessageBus
from kubemin_agent.providers.base import LLMProvider, LLMResponse


class CaptureProvider(LLMProvider):
    """Capture messages passed into chat calls for assertion."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[list[dict[str, Any]]] = []

    async def chat(self, messages, tools=None, model=None, max_tokens=4096, temperature=0.7):  # type: ignore[override]
        self.calls.append(messages)
        return LLMResponse(content="loop-ok")

    def get_default_model(self) -> str:
        return "stub"


def _seed_history(loop: AgentLoop, turns: int = 12) -> None:
    for i in range(turns):
        loop.sessions.save_turn(
            "cli:direct",
            f"user-{i} " + ("u" * 180),
            f"assistant-{i} " + ("a" * 180),
        )


@pytest.mark.asyncio
async def test_agent_loop_adds_task_anchor_and_budgeted_history(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    provider = CaptureProvider()
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=workspace,
        max_context_tokens=440,
        min_recent_history_messages=2,
        task_anchor_max_chars=80,
        history_message_max_chars=90,
    )
    _seed_history(loop, turns=12)

    result = await loop.process_direct("请长流程排查并最终给出结论与建议")
    assert result == "loop-ok"
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
async def test_agent_loop_preserves_min_recent_history_under_tight_budget(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    provider = CaptureProvider()
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=workspace,
        max_context_tokens=360,
        min_recent_history_messages=3,
        task_anchor_max_chars=60,
        history_message_max_chars=70,
    )
    _seed_history(loop, turns=8)

    await loop.process_direct("持续执行直到完成目标")
    call_messages = provider.calls[0]
    history_slice = call_messages[2:-2]

    assert len(history_slice) >= 3
