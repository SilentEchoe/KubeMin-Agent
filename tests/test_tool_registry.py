"""Tests for ToolRegistry behavior."""

from __future__ import annotations

from typing import Any

import pytest

from kubemin_agent.agent.tools.base import Tool
from kubemin_agent.agent.tools.registry import ToolRegistry


class DummyTool(Tool):
    @property
    def name(self) -> str:
        return "dummy"

    @property
    def description(self) -> str:
        return "dummy tool"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        }

    async def execute(self, **kwargs: Any) -> str:
        return str(kwargs["value"])


class FailingTool(DummyTool):
    async def execute(self, **kwargs: Any) -> str:
        raise RuntimeError("failed")


def test_registry_register_and_lookup() -> None:
    registry = ToolRegistry()
    tool = DummyTool()

    registry.register(tool)
    assert registry.has("dummy") is True
    assert registry.get("dummy") is tool
    assert "dummy" in registry
    assert len(registry) == 1
    assert registry.tool_names == ["dummy"]
    assert registry.get_definitions()[0]["function"]["name"] == "dummy"

    registry.unregister("dummy")
    assert registry.has("dummy") is False
    assert registry.get("dummy") is None


@pytest.mark.asyncio
async def test_registry_execute_handles_errors() -> None:
    registry = ToolRegistry()
    registry.register(DummyTool())

    result_ok = await registry.execute("dummy", {"value": "ok"})
    assert result_ok == "ok"

    result_missing = await registry.execute("missing", {})
    assert "not found" in result_missing

    result_invalid = await registry.execute("dummy", {})
    assert "Invalid parameters" in result_invalid


@pytest.mark.asyncio
async def test_registry_execute_wraps_tool_exception() -> None:
    registry = ToolRegistry()
    registry.register(FailingTool())
    result = await registry.execute("dummy", {"value": "x"})
    assert "Error executing dummy" in result
