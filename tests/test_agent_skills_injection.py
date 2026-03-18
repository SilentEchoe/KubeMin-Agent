"""Tests for control-plane agent skill prompt injection."""

from __future__ import annotations

from pathlib import Path

import pytest

from kubemin_agent.agents.k8s_agent import K8sAgent
from kubemin_agent.agents.orchestrator_agent import OrchestratorAgent
from kubemin_agent.agents.workflow_agent import WorkflowAgent
from kubemin_agent.providers.base import LLMProvider, LLMResponse
from kubemin_agent.session.manager import SessionManager


class StubProvider(LLMProvider):
    """Minimal provider for agent construction in tests."""

    async def chat(self, messages, tools=None, model=None, max_tokens=4096, temperature=0.7):
        return LLMResponse(content="ok")

    def get_default_model(self) -> str:
        return "stub"


@pytest.fixture
def sessions(tmp_path: Path) -> SessionManager:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return SessionManager(workspace)


def test_k8s_agent_prompt_injects_k8s_skill(tmp_path: Path, sessions: SessionManager) -> None:
    workspace = tmp_path / "workspace"
    agent = K8sAgent(provider=StubProvider(), sessions=sessions, workspace=workspace)
    prompt = agent._build_system_prompt_with_skills("排查 pod crashloopbackoff")
    assert "### Skill: k8s-diagnosis" in prompt


def test_workflow_agent_prompt_injects_workflow_skill(
    tmp_path: Path,
    sessions: SessionManager,
) -> None:
    workspace = tmp_path / "workspace"
    agent = WorkflowAgent(provider=StubProvider(), sessions=sessions, workspace=workspace)
    prompt = agent._build_system_prompt_with_skills("帮我生成 workflow yaml")
    assert "### Skill: workflow-authoring" in prompt


def test_orchestrator_prompt_injects_delegation_skill(
    tmp_path: Path,
    sessions: SessionManager,
) -> None:
    workspace = tmp_path / "workspace"
    agent = OrchestratorAgent(provider=StubProvider(), sessions=sessions, workspace=workspace)
    prompt = agent._build_system_prompt_with_skills("分析线上告警并处理")
    assert "### Skill: orchestrator-delegation" in prompt
