import json
from pathlib import Path

import pytest

from kubemin_agent.agent.memory.manager import MemoryManager
from kubemin_agent.agent.memory.scope import MemoryScope
from kubemin_agent.agent.memory.security import MemorySecurityError


def test_team_dream_draft_uses_only_team_sessions_and_does_not_auto_write(tmp_path: Path) -> None:
    manager = MemoryManager(tmp_path)
    team_scope = MemoryScope("tenant", "alice", "k8s", team_id="platform")
    teammate_scope = MemoryScope("tenant", "bob", "k8s", team_id="platform")
    private_scope = MemoryScope("tenant", "alice", "k8s")
    other_team_scope = MemoryScope("tenant", "carol", "k8s", team_id="payments")

    manager.sync_turn(
        team_scope,
        "team:a",
        "团队约定: remember team prefers dry-run reviews",
        "noted",
        "req-a",
    )
    manager.sync_turn(
        teammate_scope,
        "team:b",
        "团队规范: project changes need reviewer approval",
        "noted",
        "req-b",
    )
    manager.sync_turn(
        private_scope,
        "dm:a",
        "团队约定: private note should not become team memory",
        "noted",
        "req-c",
    )
    manager.sync_turn(
        other_team_scope,
        "team:c",
        "团队约定: payments team has a private convention",
        "noted",
        "req-d",
    )

    draft = manager.create_dream_draft(team_scope, target_scope="team", source="manual")

    assert Path(draft.path).exists()
    assert len(draft.items) == 2
    assert {item.source_session_key for item in draft.items} == {"team:a", "team:b"}
    assert all(item.target == "team" for item in draft.items)
    assert manager.builtin.read_team(team_scope) == ""

    dry_run_item = next(item.item_id for item in draft.items if "dry-run" in item.content)
    result = manager.apply_dream_draft_item(draft.draft_id, dry_run_item)

    assert result.changed is True
    assert "dry-run reviews" in manager.builtin.read_team(team_scope)


def test_personal_dream_due_uses_turn_threshold(tmp_path: Path) -> None:
    manager = MemoryManager(tmp_path, dream_turn_threshold=2)
    scope = MemoryScope("tenant", "alice", "general")
    manager.sync_turn(scope, "dm:a", "hello", "hi", "req-a")
    manager.sync_turn(scope, "dm:b", "remember my preference for short answers", "noted", "req-b")

    due = manager.check_dream_due(scope)

    assert due.due is True
    assert due.personal_turn_count == 2
    assert any("personal session turn threshold" in reason for reason in due.reasons)


def test_team_dream_requires_team_scope(tmp_path: Path) -> None:
    manager = MemoryManager(tmp_path)
    scope = MemoryScope("tenant", "alice", "general")

    with pytest.raises(ValueError, match="team_id"):
        manager.create_dream_draft(scope, target_scope="team")


def test_apply_dream_draft_item_rescans_unsafe_content(tmp_path: Path) -> None:
    manager = MemoryManager(tmp_path)
    scope = MemoryScope("tenant", "alice", "general")
    manager.sync_turn(
        scope,
        "dm:a",
        "remember my preference for concise answers",
        "noted",
        "req-a",
    )
    draft = manager.create_dream_draft(scope, target_scope="personal", source="manual")
    path = Path(draft.path)
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    records[1]["content"] = "api_key = 'abcdefghi123456'"
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(MemorySecurityError):
        manager.apply_dream_draft_item(draft.draft_id, "item-1")

    assert manager.builtin.read_user(scope) == ""
