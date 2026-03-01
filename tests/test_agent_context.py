"""Tests for ContextBuilder."""

from pathlib import Path

import pytest

from kubemin_agent.agent.context import ContextBuilder


@pytest.fixture
def workspace(tmp_path: Path):
    """Temporary workspace."""
    # Setup some dummy bootstrap files
    for f in ContextBuilder.BOOTSTRAP_FILES:
        (tmp_path / f).write_text(f"Dummy content for {f}", encoding="utf-8")
    return tmp_path


def test_context_builder_init(workspace):
    """Test initialization and default property clamps."""
    # Should enforce minimums
    ctx = ContextBuilder(
        workspace,
        max_context_tokens=10,  # Should clamp to 512
        min_recent_history_messages=-5,  # Should clamp to 0
        task_anchor_max_chars=10,  # Should clamp to 120
        history_message_max_chars=10,  # Should clamp to 120
    )
    assert ctx.max_context_tokens == 512
    assert ctx.min_recent_history_messages == 0
    assert ctx.task_anchor_max_chars == 120
    assert ctx.history_message_max_chars == 120


def test_build_system_prompt(workspace):
    """Test generating full system prompt."""
    ctx = ContextBuilder(workspace)
    prompt = ctx.build_system_prompt()

    assert "# KubeMin-Agent" in prompt
    assert "Dummy content for AGENTS.md" in prompt
    assert "Dummy content for SOUL.md" in prompt


def test_build_task_anchor_and_reminder(workspace):
    """Test task anchors and reminders generation with truncation."""
    ctx = ContextBuilder(workspace, task_anchor_max_chars=200)

    short_task = "List pods."
    anchor = ctx.build_task_anchor(short_task)
    assert "Primary objective:\nList pods." in anchor

    reminder = ctx.build_task_reminder(short_task)
    assert "[TASK REMINDER]\nList pods." in reminder

    # Test truncation
    long_task = "A" * 500
    anchor_truncated = ctx.build_task_anchor(long_task)
    assert "A" * 140 in anchor_truncated
    assert "A" * 60 in anchor_truncated
    assert "...[truncated 300 chars]..." in anchor_truncated


def test_select_history_within_budget(workspace):
    """Test history selection when everything fits perfectly."""
    ctx = ContextBuilder(workspace, max_context_tokens=1000)

    history = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]

    selected = ctx._select_history_for_budget(
        history=history,
        current_message="How are you?",
        system_prompt="System prompt",
        task_anchor="Task anchor"
    )

    assert len(selected) == 2
    assert selected[0]["content"] == "Hello"
    assert selected[1]["content"] == "Hi there!"


def test_select_history_exceeding_budget(workspace):
    """Test history selection when things are too large and get truncated/omitted."""
    # 512 tokens is ~2048 chars
    ctx = ContextBuilder(
        workspace,
        max_context_tokens=512,  # min forced by init
        min_recent_history_messages=1,
        history_message_max_chars=500
    )

    # Create massive history
    history = [
        {"role": "user", "content": "Early message " * 100}, # Should be omitted completely
        {"role": "assistant", "content": "A" * 5000},          # Will be truncated by max_chars to 500
        {"role": "user", "content": "B" * 5000},               # Will be truncated by max_chars to 500
    ]

    # 1000 chars * 2 = 2000 chars = ~500 tokens. This gets very close to the budget.
    system_prompt = "SYS " * 10
    task_anchor = "ANCHOR " * 10

    selected = ctx._select_history_for_budget(
        history=history,
        current_message="New task here",
        system_prompt=system_prompt,
        task_anchor=task_anchor
    )

    # Because B*5000 is the most recent, it should definitely be included, but truncated to 500 chars
    # (or severely clipped if budget is violently constrained).
    assert len(selected) >= 1
    assert "B" * 120 in selected[-1]["content"] # At least 120 chars survive via clipping
    assert "truncated" in selected[-1]["content"]


def test_select_history_empty_but_forced(workspace):
    """Test history fallback when budget exhausted before even reading latest."""
    ctx = ContextBuilder(
        workspace,
        max_context_tokens=512,
        min_recent_history_messages=0,
    )

    # Make system prompt consume the entire token budget + more
    system_prompt = "A" * 3000

    history = [
        {"role": "user", "content": "I am a very very important context message."}
    ]

    selected = ctx._select_history_for_budget(
        history=history,
        current_message="Hi",
        system_prompt=system_prompt,
        task_anchor="Anchor"
    )

    # min_recent is 0, but if selected is empty, it forces the last one anyway.
    assert len(selected) == 1
    assert "I am a very very important" in selected[0]["content"]


def test_add_messages_helpers(workspace):
    """Test assistant and tool result helpers."""
    ctx = ContextBuilder(workspace)
    msgs = []

    # Add assistant
    ctx.add_assistant_message(msgs, "thinking", [{"id": "t1", "name": "foo", "arguments": {}}])
    assert len(msgs) == 1
    assert msgs[0]["role"] == "assistant"
    assert msgs[0]["tool_calls"][0]["id"] == "t1"

    # Add tool result
    ctx.add_tool_result(msgs, "t1", "foo", "Success")
    assert len(msgs) == 2
    assert msgs[1]["role"] == "tool"
    assert msgs[1]["content"] == "Success"
