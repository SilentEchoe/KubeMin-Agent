import asyncio
from typing import Any

from agent_core.tools import Tool, ToolRegistry


class SampleTool(Tool):
    @property
    def name(self) -> str:
        return "sample"

    @property
    def description(self) -> str:
        return "sample test tool"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 2},
                "count": {"type": "integer", "minimum": 1, "maximum": 5},
            },
            "required": ["query", "count"],
        }

    async def execute(self, **kwargs: Any) -> str:
        return "ok"


def test_tool_validate_missing_required() -> None:
    tool = SampleTool()
    errors = tool.validate_params({"query": "hello"})
    assert "missing required count" in "; ".join(errors)


def test_tool_validate_type_and_range() -> None:
    tool = SampleTool()
    errors = tool.validate_params({"query": "hello", "count": 0})
    assert any("count must be >= 1" in e for e in errors)

    errors = tool.validate_params({"query": "hello", "count": "1"})
    assert any("count should be integer" in e for e in errors)


def test_registry_returns_validation_error() -> None:
    registry = ToolRegistry()
    registry.register(SampleTool())
    result = asyncio.run(registry.execute("sample", {"query": "hello"}))
    assert "Invalid parameters" in result
