"""Tests for PatrolAgent initialization and properties."""

from __future__ import annotations

from pathlib import Path

import pytest

from kubemin_agent.agents.patrol_agent import PatrolAgent
from kubemin_agent.config.schema import PatrolConfig
from kubemin_agent.providers.base import LLMProvider, LLMResponse
from kubemin_agent.session.manager import SessionManager


class StubProvider(LLMProvider):
    """Minimal stub provider for unit tests."""

    async def chat(self, messages, tools=None, model=None, max_tokens=4096, temperature=0.7):
        return LLMResponse(content="stub-ok")

    def get_default_model(self) -> str:
        return "stub"


@pytest.fixture
def patrol_agent(tmp_path: Path) -> PatrolAgent:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sessions = SessionManager(workspace)
    return PatrolAgent(provider=StubProvider(), sessions=sessions, workspace=workspace)


@pytest.fixture
def patrol_agent_with_kubemin(tmp_path: Path) -> PatrolAgent:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sessions = SessionManager(workspace)
    return PatrolAgent(
        provider=StubProvider(),
        sessions=sessions,
        workspace=workspace,
        kubemin_api_base="http://kubemin.local:8080",
        kubemin_namespace="prod",
    )


class TestPatrolAgentProperties:
    """Test basic agent properties."""

    def test_name(self, patrol_agent: PatrolAgent) -> None:
        assert patrol_agent.name == "patrol"

    def test_description_mentions_health(self, patrol_agent: PatrolAgent) -> None:
        assert "health" in patrol_agent.description.lower()

    def test_description_mentions_events(self, patrol_agent: PatrolAgent) -> None:
        assert "event" in patrol_agent.description.lower()

    def test_description_mentions_kubemin_cli(self, patrol_agent: PatrolAgent) -> None:
        assert "kubemin-cli" in patrol_agent.description.lower()

    def test_allowed_tools(self, patrol_agent: PatrolAgent) -> None:
        assert set(patrol_agent.allowed_tools) == {
            "kubectl", "run_command", "read_file", "write_file", "kubemin_cli",
        }


class TestPatrolAgentTools:
    """Test that tools are correctly registered and filtered."""

    def test_registered_tools_match_allowlist(self, patrol_agent: PatrolAgent) -> None:
        registered = set(patrol_agent.tools.tool_names)
        assert registered == set(patrol_agent.allowed_tools)

    def test_kubectl_tool_registered(self, patrol_agent: PatrolAgent) -> None:
        assert "kubectl" in patrol_agent.tools.tool_names

    def test_write_file_tool_registered(self, patrol_agent: PatrolAgent) -> None:
        assert "write_file" in patrol_agent.tools.tool_names

    def test_kubemin_cli_tool_registered(self, patrol_agent: PatrolAgent) -> None:
        assert "kubemin_cli" in patrol_agent.tools.tool_names


class TestPatrolAgentSkills:
    """Test that patrol skill knowledge is loaded into the system prompt."""

    def test_system_prompt_contains_patrol_identity(self, patrol_agent: PatrolAgent) -> None:
        prompt = patrol_agent.system_prompt
        assert "PatrolAgent" in prompt

    def test_system_prompt_contains_readonly_constraint(self, patrol_agent: PatrolAgent) -> None:
        prompt = patrol_agent.system_prompt
        assert "READ-ONLY" in prompt

    def test_system_prompt_mentions_kubemin_platform_strategy(self, patrol_agent: PatrolAgent) -> None:
        prompt = patrol_agent.system_prompt
        assert "kubemin-cli" in prompt.lower() or "kubemin_cli" in prompt.lower()

    def test_active_prompt_contains_patrol_skill(self, patrol_agent: PatrolAgent) -> None:
        prompt = patrol_agent._build_system_prompt_with_skills("执行平台巡检并生成日报")
        assert "=== ACTIVE SKILLS ===" in prompt
        assert "### Skill: patrol" in prompt
        assert "STRATEGY 1" in prompt
        assert "健康评分" in prompt


class TestPatrolConfig:
    """Test PatrolConfig defaults."""

    def test_default_disabled(self) -> None:
        config = PatrolConfig()
        assert config.enabled is False

    def test_default_schedule(self) -> None:
        config = PatrolConfig()
        assert config.schedule == "0 9 * * *"

    def test_default_channel(self) -> None:
        config = PatrolConfig()
        assert config.channel == "patrol"

    def test_default_message_not_empty(self) -> None:
        config = PatrolConfig()
        assert len(config.message) > 0
