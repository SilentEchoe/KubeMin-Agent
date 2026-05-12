from pathlib import Path

from kubemin_agent.agent.memory.manager import MemoryManager
from kubemin_agent.agent.memory.scope import MemoryScope
from kubemin_agent.session.manager import SessionManager


def test_session_search_is_scoped_by_tenant_and_user(tmp_path: Path) -> None:
    manager = MemoryManager(tmp_path)
    alpha = MemoryScope("tenant-a", "user-1", "k8s")
    beta_tenant = MemoryScope("tenant-b", "user-1", "k8s")
    beta_user = MemoryScope("tenant-a", "user-2", "k8s")

    manager.sync_turn(alpha, "telegram:1", "pod crashloop", "restart count is high", "req-a")
    manager.sync_turn(beta_tenant, "telegram:2", "pod crashloop", "secret tenant result", "req-b")
    manager.sync_turn(beta_user, "telegram:3", "pod crashloop", "secret user result", "req-c")

    results = manager.search_sessions(alpha, "crashloop", top_k=10)

    assert len(results) == 1
    assert results[0].session_key == "telegram:1"
    assert "secret" not in results[0].snippet


def test_session_search_optional_agent_filter(tmp_path: Path) -> None:
    manager = MemoryManager(tmp_path)
    k8s = MemoryScope("tenant", "user", "k8s")
    workflow = MemoryScope("tenant", "user", "workflow")

    manager.sync_turn(k8s, "cli:1", "validate yaml", "k8s result", "req-1")
    manager.sync_turn(workflow, "cli:2", "validate yaml", "workflow result", "req-2")

    results = manager.search_sessions(k8s, "validate", agent_name="workflow")

    assert len(results) == 1
    assert results[0].agent_name == "workflow"


def test_session_manager_syncs_turns_into_search_index(tmp_path: Path) -> None:
    memory = MemoryManager(tmp_path)
    sessions = SessionManager(tmp_path, memory_manager=memory)
    scope = MemoryScope("tenant", "user", "general")

    sessions.save_turn(
        "cli:direct",
        "remember cluster budget",
        "cluster budget discussion saved",
        scope=scope,
        request_id="req-1",
    )

    assert len(sessions.get_history("cli:direct")) == 2
    results = memory.search_sessions(scope, "budget")
    assert len(results) == 1
    assert results[0].request_id == "req-1"
