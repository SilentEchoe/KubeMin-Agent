"""Tests for DelegateAgentTool and OrchestratorAgent."""

from __future__ import annotations

from pathlib import Path

import pytest

from kubemin_agent.agent.tools.delegate import DelegateAgentTool, create_delegate_tools
from kubemin_agent.control.registry import AgentRegistry
from kubemin_agent.providers.base import LLMProvider, LLMResponse
from kubemin_agent.session.manager import SessionManager


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class _ToolNames:
    tool_names: list[str] = []


class StubAgent:
    """Minimal agent for testing delegation."""

    def __init__(self, name: str, description: str = "") -> None:
        self._name = name
        self._description = description or f"stub agent: {name}"
        self.tools = _ToolNames()
        self.last_message = ""
        self.last_session_key = ""

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    async def run(self, message: str, session_key: str, request_id: str = "") -> str:
        self.last_message = message
        self.last_session_key = session_key
        return f"result-from-{self._name}: {message}"


class EmptyAgent(StubAgent):
    """Agent that returns empty string."""

    async def run(self, message: str, session_key: str, request_id: str = "") -> str:
        return ""


class FailingAgent(StubAgent):
    """Agent that raises an exception."""

    async def run(self, message: str, session_key: str, request_id: str = "") -> str:
        raise RuntimeError("deliberate failure")


# ---------------------------------------------------------------------------
# DelegateAgentTool tests
# ---------------------------------------------------------------------------

class TestDelegateAgentTool:
    def test_name_is_delegate_prefix(self) -> None:
        agent = StubAgent("k8s")
        tool = DelegateAgentTool(agent)
        assert tool.name == "delegate_k8s"

    def test_description_includes_agent_description(self) -> None:
        agent = StubAgent("k8s", "Handles K8s operations")
        tool = DelegateAgentTool(agent)
        assert "Handles K8s operations" in tool.description

    def test_parameters_schema(self) -> None:
        tool = DelegateAgentTool(StubAgent("k8s"))
        params = tool.parameters
        assert params["type"] == "object"
        assert "task" in params["properties"]
        assert "task" in params["required"]

    def test_to_schema_format(self) -> None:
        tool = DelegateAgentTool(StubAgent("k8s"))
        schema = tool.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "delegate_k8s"

    @pytest.mark.asyncio
    async def test_execute_delegates_to_agent(self) -> None:
        agent = StubAgent("k8s")
        tool = DelegateAgentTool(agent, session_key="cli:test", request_id="req-1")
        result = await tool.execute(task="get pods")
        assert "result-from-k8s" in result
        assert "get pods" in result
        assert agent.last_message == "get pods"
        assert agent.last_session_key == "cli:test"

    @pytest.mark.asyncio
    async def test_execute_empty_task_returns_error(self) -> None:
        tool = DelegateAgentTool(StubAgent("k8s"))
        result = await tool.execute(task="")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_execute_missing_task_returns_error(self) -> None:
        tool = DelegateAgentTool(StubAgent("k8s"))
        result = await tool.execute()
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_execute_empty_response_gives_fallback(self) -> None:
        tool = DelegateAgentTool(EmptyAgent("k8s"))
        result = await tool.execute(task="anything")
        assert "empty response" in result.lower()

    @pytest.mark.asyncio
    async def test_execute_handles_agent_error(self) -> None:
        tool = DelegateAgentTool(FailingAgent("k8s"))
        result = await tool.execute(task="anything")
        assert "Error" in result
        assert "deliberate failure" in result

    def test_update_context(self) -> None:
        tool = DelegateAgentTool(StubAgent("k8s"), session_key="old", request_id="old-r")
        tool.update_context("new-session", "new-req")
        assert tool._session_key == "new-session"
        assert tool._request_id == "new-req"

    def test_validate_params_missing_required(self) -> None:
        tool = DelegateAgentTool(StubAgent("k8s"))
        errors = tool.validate_params({})
        assert len(errors) > 0
        assert any("task" in e for e in errors)

    def test_validate_params_ok(self) -> None:
        tool = DelegateAgentTool(StubAgent("k8s"))
        errors = tool.validate_params({"task": "do something"})
        assert errors == []


# ---------------------------------------------------------------------------
# create_delegate_tools tests
# ---------------------------------------------------------------------------

class TestCreateDelegateTools:
    def test_creates_tools_for_all_agents(self) -> None:
        registry = AgentRegistry()
        registry.register(StubAgent("general"))
        registry.register(StubAgent("k8s"))
        tools = create_delegate_tools(registry)
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert names == {"delegate_general", "delegate_k8s"}

    def test_excludes_specified_agents(self) -> None:
        registry = AgentRegistry()
        registry.register(StubAgent("general"))
        registry.register(StubAgent("k8s"))
        registry.register(StubAgent("orchestrator"))
        tools = create_delegate_tools(registry, exclude={"orchestrator"})
        names = {t.name for t in tools}
        assert "delegate_orchestrator" not in names
        assert len(tools) == 2

    def test_empty_registry(self) -> None:
        registry = AgentRegistry()
        tools = create_delegate_tools(registry)
        assert tools == []


# ---------------------------------------------------------------------------
# OrchestratorAgent tests
# ---------------------------------------------------------------------------

class StubProvider(LLMProvider):
    async def chat(self, messages, tools=None, model=None, max_tokens=4096, temperature=0.7):
        return LLMResponse(content="orchestrator-response")

    def get_default_model(self) -> str:
        return "stub"


class TestOrchestratorAgent:
    def _create_orchestrator(self, tmp_path: Path, delegate_tools=None):
        from kubemin_agent.agents.orchestrator_agent import OrchestratorAgent

        workspace = tmp_path / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        sessions = SessionManager(workspace)
        return OrchestratorAgent(
            provider=StubProvider(),
            sessions=sessions,
            delegate_tools=delegate_tools or [],
            workspace=workspace,
        )

    def test_name(self, tmp_path: Path) -> None:
        agent = self._create_orchestrator(tmp_path)
        assert agent.name == "orchestrator"

    def test_has_direct_tools(self, tmp_path: Path) -> None:
        agent = self._create_orchestrator(tmp_path)
        tool_names = agent.tools.tool_names
        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "run_command" in tool_names
        assert "kubectl" in tool_names
        assert "validate_yaml" in tool_names

    def test_has_delegate_tools(self, tmp_path: Path) -> None:
        delegate = DelegateAgentTool(StubAgent("k8s"))
        agent = self._create_orchestrator(tmp_path, delegate_tools=[delegate])
        assert "delegate_k8s" in agent.tools.tool_names

    def test_system_prompt_mentions_both_tool_types(self, tmp_path: Path) -> None:
        delegate = DelegateAgentTool(StubAgent("k8s"))
        agent = self._create_orchestrator(tmp_path, delegate_tools=[delegate])
        prompt = agent.system_prompt
        assert "Direct Tools" in prompt
        assert "Delegate Tools" in prompt
        assert "delegate_k8s" in prompt

    @pytest.mark.asyncio
    async def test_run_returns_response(self, tmp_path: Path) -> None:
        agent = self._create_orchestrator(tmp_path)
        result = await agent.run("hello", "cli:test")
        assert "orchestrator-response" in result

    def test_update_delegate_context(self, tmp_path: Path) -> None:
        delegate = DelegateAgentTool(StubAgent("k8s"))
        agent = self._create_orchestrator(tmp_path, delegate_tools=[delegate])
        agent.update_delegate_context("new-sess", "new-req")
        assert delegate._session_key == "new-sess"
        assert delegate._request_id == "new-req"

    def test_no_allowed_tools_restriction(self, tmp_path: Path) -> None:
        """Orchestrator should not restrict tools via allowlist."""
        agent = self._create_orchestrator(tmp_path)
        # All registered tools should remain available
        assert len(agent.tools) >= 5
