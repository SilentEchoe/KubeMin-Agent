"""Tests for session/audit retention and rotation behavior."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

from kubemin_agent.control.audit import AuditLog
from kubemin_agent.session.manager import SessionManager


def test_session_manager_respects_cache_limit(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    manager = SessionManager(workspace, max_history=4, cache_message_limit=4)

    for idx in range(3):
        manager.save_turn("cli:test", f"user-{idx}", f"assistant-{idx}")

    assert len(manager._cache["cli:test"]) == 4
    history = manager.get_history("cli:test")
    assert [msg["content"] for msg in history] == [
        "user-1",
        "assistant-1",
        "user-2",
        "assistant-2",
    ]


def test_session_manager_truncates_large_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    manager = SessionManager(
        workspace,
        max_history=2,
        cache_message_limit=4,
        file_max_mb=1,
    )
    payload = "x" * 300_000
    session_key = "cli:big"

    for idx in range(4):
        manager.save_turn(session_key, f"{idx}:{payload}", f"{idx}:{payload}")

    path = manager._session_path(session_key)
    assert path.exists()
    assert path.stat().st_size <= 1 * 1024 * 1024


def test_session_manager_removes_expired_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    stale_file = sessions_dir / "stale.jsonl"
    stale_file.write_text("{}", encoding="utf-8")

    old_time = datetime.now() - timedelta(days=45)
    os.utime(stale_file, (old_time.timestamp(), old_time.timestamp()))

    SessionManager(workspace, retention_days=30)
    assert not stale_file.exists()


def test_audit_log_rotates_when_file_too_large(tmp_path: Path) -> None:
    audit = AuditLog(tmp_path, file_max_mb=1)
    content = "x" * 450_000

    for idx in range(5):
        audit._write({"type": "rotation-test", "index": idx, "payload": content})

    files = sorted((tmp_path / "audit").glob("*.jsonl"))
    assert len(files) >= 2


def test_audit_log_removes_expired_files(tmp_path: Path) -> None:
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    stale_file = audit_dir / "old.jsonl"
    stale_file.write_text("{}", encoding="utf-8")
    old_time = datetime.now() - timedelta(days=45)
    os.utime(stale_file, (old_time.timestamp(), old_time.timestamp()))

    AuditLog(tmp_path, retention_days=30)
    assert not stale_file.exists()
