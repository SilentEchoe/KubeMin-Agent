from pathlib import Path

import pytest

from kubemin_agent.agent.memory.manager import MemoryManager
from kubemin_agent.agent.memory.runtime import memory_run_context
from kubemin_agent.agent.memory.scope import MemoryScope
from kubemin_agent.agent.memory.tools import MemoryUpdateTool, SessionSearchTool


def test_manager_builds_frozen_snapshot(tmp_path: Path) -> None:
    manager = MemoryManager(tmp_path)
    scope = MemoryScope("tenant", "user", "general")
    manager.update_builtin(scope, "user", "add", content="prefers short answers")

    snapshot = manager.build_system_prompt_block(scope)
    manager.update_builtin(scope, "user", "add", content="new preference after snapshot")

    assert "prefers short answers" in snapshot
    assert "new preference after snapshot" not in snapshot
    assert "new preference after snapshot" in manager.build_system_prompt_block(scope)


@pytest.mark.asyncio
async def test_memory_update_tool_requires_active_scope(tmp_path: Path) -> None:
    tool = MemoryUpdateTool()

    with pytest.raises(RuntimeError, match="active MemoryManager"):
        await tool.execute(target="memory", action="add", content="hello")


@pytest.mark.asyncio
async def test_memory_update_tool_uses_runtime_scope(tmp_path: Path) -> None:
    manager = MemoryManager(tmp_path)
    scope = MemoryScope("tenant", "user", "k8s")
    tool = MemoryUpdateTool()

    with memory_run_context(manager, scope):
        result = await tool.execute(target="memory", action="add", content="k8s diagnosis preference")

    assert "memory added" in result
    assert "tenant" in result
    assert "k8s diagnosis preference" in manager.builtin.read_memory(scope)


@pytest.mark.asyncio
async def test_memory_update_tool_uses_runtime_team_scope(tmp_path: Path) -> None:
    manager = MemoryManager(tmp_path)
    scope = MemoryScope("tenant", "user", "k8s", team_id="platform")
    tool = MemoryUpdateTool()

    with memory_run_context(manager, scope):
        result = await tool.execute(
            target="team",
            action="add",
            content="team prefers reviewed dry-run changes",
        )

    assert "memory added" in result
    assert "platform" in result
    assert "reviewed dry-run" in manager.builtin.read_team(scope)


@pytest.mark.asyncio
async def test_memory_update_tool_rejects_team_target_without_team_scope(tmp_path: Path) -> None:
    manager = MemoryManager(tmp_path)
    scope = MemoryScope("tenant", "user", "k8s")
    tool = MemoryUpdateTool()

    with memory_run_context(manager, scope):
        with pytest.raises(ValueError, match="team_id"):
            await tool.execute(target="team", action="add", content="team norm")


@pytest.mark.asyncio
async def test_session_search_tool_uses_runtime_scope(tmp_path: Path) -> None:
    manager = MemoryManager(tmp_path)
    scope = MemoryScope("tenant", "user", "k8s")
    other = MemoryScope("tenant", "other", "k8s")
    manager.sync_turn(scope, "cli:a", "CrashLoopBackOff", "restart probe failed", "req-a")
    manager.sync_turn(other, "cli:b", "CrashLoopBackOff", "private other result", "req-b")

    tool = SessionSearchTool()
    with memory_run_context(manager, scope):
        result = await tool.execute(query="CrashLoopBackOff", top_k=5)

    assert "cli:a" in result
    assert "cli:b" not in result
    assert "private other result" not in result


@pytest.mark.asyncio
async def test_session_search_tool_uses_team_scope_mode(tmp_path: Path) -> None:
    manager = MemoryManager(tmp_path)
    alice = MemoryScope("tenant", "alice", "k8s", team_id="platform")
    bob = MemoryScope("tenant", "bob", "k8s", team_id="platform")
    private_alice = MemoryScope("tenant", "alice", "k8s")
    manager.sync_turn(alice, "team:a", "remember team budget", "team result", "req-a")
    manager.sync_turn(bob, "team:b", "remember team budget", "bob result", "req-b")
    manager.sync_turn(private_alice, "dm:a", "remember team budget", "private result", "req-c")

    tool = SessionSearchTool()
    with memory_run_context(manager, alice):
        result = await tool.execute(query="budget", scope="auto", top_k=5)

    assert "team:a" in result
    assert "team:b" in result
    assert "dm:a" not in result
