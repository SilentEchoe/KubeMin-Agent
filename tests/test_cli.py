"""Tests for the KubeMin-Agent CLI."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from kubemin_agent.cli.commands import app

runner = CliRunner()


@pytest.fixture
def mock_config(tmp_path: Path):
    """Fixture to provide a mocked config and workspace."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    mock_cfg = MagicMock()
    mock_cfg.workspace_path = workspace
    mock_cfg.get_api_key.return_value = "sk-1234567890"
    mock_cfg.get_api_base.return_value = "https://api.openai.com/v1"

    mock_cfg.agents.defaults.model = "gpt-4o"
    mock_cfg.agents.defaults.max_tokens = 2000
    mock_cfg.agents.defaults.max_context_tokens = 6000
    mock_cfg.agents.defaults.min_recent_history_messages = 4
    mock_cfg.agents.defaults.task_anchor_max_chars = 600
    mock_cfg.agents.defaults.history_message_max_chars = 1200
    mock_cfg.agents.defaults.memory_backend = "file"
    mock_cfg.agents.defaults.memory_top_k = 5
    mock_cfg.agents.defaults.memory_context_max_chars = 1400
    mock_cfg.agents.defaults.temperature = 0.5
    mock_cfg.agents.defaults.max_tool_iterations = 20

    mock_cfg.control.enabled = False
    mock_cfg.control.max_parallelism = 5
    mock_cfg.control.fail_fast = True

    mock_cfg.evaluation.enabled = False
    mock_cfg.evaluation.mode = "standard"
    mock_cfg.evaluation.warn_threshold = 0.8
    mock_cfg.evaluation.llm_judge_enabled = False
    mock_cfg.evaluation.trace_capture = False
    mock_cfg.evaluation.max_trace_steps = 50

    mock_cfg.validator.policy_level = "strict"
    mock_cfg.channels.telegram.enabled = False
    mock_cfg.kubemin.api_base = None

    return mock_cfg


@patch("kubemin_agent.cli.commands.save_default_config")
@patch("kubemin_agent.cli.commands.load_config")
@patch("kubemin_agent.cli.commands.ensure_workspace")
def test_cli_onboard(mock_ensure, mock_load, mock_save, mock_config, tmp_path):
    """Test the onboard command."""
    mock_save.return_value = tmp_path / "config.yaml"
    mock_load.return_value = mock_config
    mock_ensure.return_value = tmp_path / "workspace"

    result = runner.invoke(app, ["onboard"])
    assert result.exit_code == 0
    assert "Config created at:" in result.stdout
    assert "Workspace initialized at:" in result.stdout


@patch("kubemin_agent.cli.commands.load_config")
def test_cli_status(mock_load, mock_config):
    """Test the status command output rendering."""
    mock_load.return_value = mock_config

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "KubeMin-Agent Status" in result.stdout
    assert "gpt-4o" in result.stdout
    assert "...34567890" in result.stdout  # masked key


@patch("kubemin_agent.cli.commands.load_config")
@patch("kubemin_agent.cli.commands.ensure_workspace")
def test_cli_agent_no_key(mock_ensure, mock_load, mock_config, tmp_path):
    """Test agent failing gracefully without an API key."""
    mock_ensure.return_value = tmp_path
    mock_config.get_api_key.return_value = None
    mock_load.return_value = mock_config

    result = runner.invoke(app, ["agent", "-m", "hello"])
    assert result.exit_code == 1
    assert "No API key configured" in result.stdout


@patch("kubemin_agent.cli.commands.load_config")
@patch("kubemin_agent.cli.commands.ensure_workspace")
@patch("kubemin_agent.agent.loop.AgentLoop")
def test_cli_agent_direct_message(mock_agent_loop_cls, mock_ensure, mock_load, mock_config, tmp_path):
    """Test agent sending a direct message in legacy mode."""
    mock_ensure.return_value = tmp_path
    mock_load.return_value = mock_config

    mock_loop_instance = mock_agent_loop_cls.return_value

    # Needs to match an AsyncMock result since process_direct is async
    async def mock_process(msg):
        return f"Echo: {msg}"
    mock_loop_instance.process_direct.side_effect = mock_process

    result = runner.invoke(app, ["agent", "-m", "hello"])
    assert result.exit_code == 0
    assert "Echo: hello" in result.stdout
