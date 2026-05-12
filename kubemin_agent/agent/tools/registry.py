"""Tool registry."""

from __future__ import annotations

from typing import Any

from kubemin_agent.agent.tools.base import Tool


class ToolRegistry:
    """In-memory registry for agent tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register or replace a tool."""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """Remove a tool by name."""
        self._tools.pop(name, None)

    def get_definitions(self) -> list[dict[str, Any]]:
        """Return all tool schemas."""
        return [tool.to_schema() for tool in self._tools.values()]

    async def execute(self, name: str, params: dict[str, Any]) -> str:
        """Execute a registered tool."""
        tool = self._tools.get(name)
        if not tool:
            return f"Error: Tool '{name}' not found"
        errors = tool.validate_params(params)
        if errors:
            return f"Error: Invalid parameters for tool '{name}': " + "; ".join(errors)
        return await tool.execute(**params)

    @property
    def tool_names(self) -> list[str]:
        """Return registered tool names."""
        return list(self._tools.keys())
