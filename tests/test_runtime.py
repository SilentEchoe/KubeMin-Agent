"""Tests for control plane runtime defaults."""

from __future__ import annotations

from pathlib import Path

import pytest

from kubemin_agent.config.schema import Config
from kubemin_agent.control.runtime import ControlPlaneRuntime
from kubemin_agent.providers.base import LLMProvider, LLMResponse


class RoutingProvider(LLMProvider):
    """Minimal provider that supports both routing and sub-agent answering."""

    async def chat(self, messages, tools=None, model=None, max_tokens=4096, temperature=0.7):
        system_content = (messages[0].get("content") or "").lower()
        if "task router for kubemin-agent" in system_content:
            return LLMResponse(content='{"agent":"general","task":"echo"}')
        return LLMResponse(content="runtime-ok")

    def get_default_model(self) -> str:
        return "stub"


@pytest.mark.asyncio
async def test_runtime_registers_default_agents_and_handles_message(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    runtime = ControlPlaneRuntime(provider=RoutingProvider(), workspace=workspace)
    assert set(runtime.registry.agent_names) == {"general", "k8s", "workflow"}
    assert runtime.scheduler.evaluator is not None

    result = await runtime.handle_message(channel="cli", chat_id="test", content="hello")
    assert "runtime-ok" in result


def test_runtime_from_config_can_disable_evaluation(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    config = Config()
    config.evaluation.enabled = False

    runtime = ControlPlaneRuntime.from_config(config, RoutingProvider(), workspace)
    assert runtime.scheduler.evaluator is None
