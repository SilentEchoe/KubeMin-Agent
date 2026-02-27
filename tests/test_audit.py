"""Tests for audit log event types."""

from __future__ import annotations

import json
from pathlib import Path

from kubemin_agent.control.audit import AuditLog


def _load_entries(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_audit_logs_reasoning_and_evaluation_events(tmp_path: Path) -> None:
    audit = AuditLog(tmp_path)

    audit.log_reasoning_step(
        session_key="cli:test",
        agent_name="general",
        task_id="t1",
        step_index=1,
        phase="tool_call",
        intent_summary="读取配置文件",
        action="tool:read_file",
        observation_summary='{"path":"config.yaml"}',
        request_id="req-1",
    )
    audit.log_evaluation(
        session_key="cli:test",
        agent_name="general",
        task_id="t1",
        overall_score=78,
        dimension_scores={"completeness": 80, "execution_health": 70, "efficiency": 85},
        passed=True,
        warn_threshold=60,
        reasons=["执行质量稳定"],
        suggestions=["保持当前策略"],
        request_id="req-1",
    )

    entries = _load_entries(audit._log_file())
    reasoning_entries = [entry for entry in entries if entry.get("type") == "reasoning_step"]
    evaluation_entries = [entry for entry in entries if entry.get("type") == "evaluation"]

    assert len(reasoning_entries) == 1
    assert reasoning_entries[0]["task_id"] == "t1"
    assert reasoning_entries[0]["phase"] == "tool_call"

    assert len(evaluation_entries) == 1
    assert evaluation_entries[0]["overall_score"] == 78
    assert evaluation_entries[0]["passed"] is True
    assert evaluation_entries[0]["warn_threshold"] == 60
