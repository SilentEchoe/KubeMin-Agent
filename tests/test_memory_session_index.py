import sqlite3
from pathlib import Path

import pytest

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


def test_session_index_migrates_existing_database_with_team_id(tmp_path: Path) -> None:
    db_path = tmp_path / "memory" / "session_search.sqlite3"
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE session_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                session_key TEXT NOT NULL,
                request_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                user_message TEXT NOT NULL,
                assistant_response TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE session_fts USING fts5(content);
            """
        )

    MemoryManager(tmp_path)

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(session_turns)").fetchall()}
    assert "team_id" in columns


def test_team_session_search_uses_team_scope_across_users(tmp_path: Path) -> None:
    manager = MemoryManager(tmp_path)
    alice = MemoryScope("tenant", "alice", "k8s", team_id="platform")
    bob = MemoryScope("tenant", "bob", "k8s", team_id="platform")
    private_alice = MemoryScope("tenant", "alice", "k8s")
    other_team = MemoryScope("tenant", "carol", "k8s", team_id="payments")

    manager.sync_turn(alice, "team:1", "remember team namespace budget", "platform result", "req-a")
    manager.sync_turn(bob, "team:2", "remember team namespace budget", "bob result", "req-b")
    manager.sync_turn(private_alice, "dm:1", "remember team namespace budget", "private result", "req-c")
    manager.sync_turn(other_team, "team:3", "remember team namespace budget", "payments result", "req-d")

    team_results = manager.search_sessions(alice, "namespace budget", top_k=10)
    private_results = manager.search_sessions(private_alice, "namespace budget", top_k=10)

    assert {item.session_key for item in team_results} == {"team:1", "team:2"}
    assert {item.session_key for item in private_results} == {"dm:1"}
    assert all("payments" not in item.snippet for item in team_results)


def test_team_session_search_requires_explicit_team_id(tmp_path: Path) -> None:
    manager = MemoryManager(tmp_path)
    scope = MemoryScope("tenant", "user", "k8s")

    with pytest.raises(ValueError, match="team_id"):
        manager.search_sessions(scope, "anything", scope_mode="team")


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
