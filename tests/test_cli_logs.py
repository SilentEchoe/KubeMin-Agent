import json

import pytest
from typer.testing import CliRunner

from kubemin_agent.cli.commands import app


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def temp_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()

    # Create some dummy audit logs
    log_file = audit_dir / "2026-02-28.jsonl"
    with open(log_file, "w") as f:
        f.write(json.dumps({
            "type": "evaluation",
            "agent_name": "k8s",
            "task_id": "test-task",
            "overall_score": 85,
            "dimension_scores": {"correctness": 90},
            "passed": True,
            "warn_threshold": 60,
            "session_key": "test-session",
            "request_id": "req-123",
            "timestamp": "2026-02-28T10:00:00"
        }) + "\n")
        f.write(json.dumps({
            "type": "reasoning_step",
            "agent_name": "k8s",
            "task_id": "test-task",
            "step_index": 1,
            "phase": "plan",
            "intent_summary": "Planning to run kubectl get pods",
            "session_key": "test-session",
            "request_id": "req-123",
            "timestamp": "2026-02-28T10:01:00"
        }) + "\n")
        f.write(json.dumps({
            "type": "dispatch",
            "target_agent": "k8s",
            "task_id": "test-task",
            "task_description": "Get pods",
            "session_key": "test-session",
            "request_id": "req-123",
            "timestamp": "2026-02-28T09:59:00"
        }) + "\n")

    # We need to mock load_config and ensure_workspace, but it's easier to mock the audit_dir
    # discovery right in the command itself or via monkeypatch.
    # Since we don't want to mess with patching internal config loads, we can mock `from kubemin_agent.cli.commands import ensure_workspace`
    return tmp_path


def test_logs_command_basic(runner, temp_workspace, monkeypatch):
    import kubemin_agent.cli.commands as commands
    class MockConfig:
        pass

    def mock_load_config(*args):
        return MockConfig()

    def mock_ensure_workspace(*args):
        return temp_workspace / "workspace"

    monkeypatch.setattr(commands, "load_config", mock_load_config)
    monkeypatch.setattr(commands, "ensure_workspace", mock_ensure_workspace)

    result = runner.invoke(app, ["logs"])
    assert result.exit_code == 0
    assert "Found 3 matching log entries" in result.output
    # Order should be chronological: DISPATCH, STEP 1, EVALUATION
    assert "DISPATCH ➔ k8s" in result.output
    assert "STEP 1" in result.output
    assert "EVALUATION" in result.output
    assert "Score: 85/60" in result.output


def test_logs_command_eval_only(runner, temp_workspace, monkeypatch):
    import kubemin_agent.cli.commands as commands
    class MockConfig:
        pass

    def mock_load_config(*args):
        return MockConfig()

    def mock_ensure_workspace(*args):
        return temp_workspace / "workspace"

    monkeypatch.setattr(commands, "load_config", mock_load_config)
    monkeypatch.setattr(commands, "ensure_workspace", mock_ensure_workspace)

    result = runner.invoke(app, ["logs", "--eval-only"])
    assert result.exit_code == 0
    assert "Found 1 matching log entries" in result.output
    assert "DISPATCH" not in result.output
    assert "STEP 1" not in result.output
    assert "EVALUATION" in result.output


def test_logs_command_filter_session(runner, temp_workspace, monkeypatch):
    import kubemin_agent.cli.commands as commands
    class MockConfig:
        pass

    def mock_load_config(*args):
        return MockConfig()

    def mock_ensure_workspace(*args):
        return temp_workspace / "workspace"

    monkeypatch.setattr(commands, "load_config", mock_load_config)
    monkeypatch.setattr(commands, "ensure_workspace", mock_ensure_workspace)

    result = runner.invoke(app, ["logs", "--session", "test-session"])
    assert result.exit_code == 0
    assert "Found 3 matching log entries" in result.output

    result = runner.invoke(app, ["logs", "--session", "other-session"])
    assert result.exit_code == 0
    assert "No matching logs found" in result.output

