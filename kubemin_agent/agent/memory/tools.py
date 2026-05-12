"""Scoped memory infrastructure tools."""

from __future__ import annotations

from typing import Any

from kubemin_agent.agent.memory.runtime import get_active_memory
from kubemin_agent.agent.tools.base import Tool


class MemoryUpdateTool(Tool):
    """Update scoped builtin USER.md or MEMORY.md."""

    @property
    def name(self) -> str:
        return "memory_update"

    @property
    def description(self) -> str:
        return "Add, replace, or remove scoped high-signal memory for the active tenant/user/agent."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string", "enum": ["user", "memory"]},
                "action": {"type": "string", "enum": ["add", "replace", "remove"]},
                "content": {"type": "string"},
                "old_text": {"type": "string"},
            },
            "required": ["target", "action"],
        }

    async def execute(
        self,
        target: str,
        action: str,
        content: str = "",
        old_text: str = "",
    ) -> str:
        manager, scope = get_active_memory()
        result = manager.update_builtin(
            scope=scope,
            target=target,
            action=action,
            content=content,
            old_text=old_text,
        )
        return (
            f"{result.message}\n"
            f"scope={scope.to_metadata()}\n"
            f"target={result.target} usage={result.usage_chars}/{result.max_chars}"
        )


class SessionSearchTool(Tool):
    """Search scoped session history."""

    @property
    def name(self) -> str:
        return "session_search"

    @property
    def description(self) -> str:
        return "Search prior turns for the active tenant/user scope using SQLite FTS5."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "top_k": {"type": "integer"},
                "agent_name": {"type": "string"},
                "session_key": {"type": "string"},
                "request_id": {"type": "string"},
            },
            "required": ["query"],
        }

    async def execute(
        self,
        query: str,
        top_k: int = 5,
        agent_name: str = "",
        session_key: str = "",
        request_id: str = "",
    ) -> str:
        manager, scope = get_active_memory()
        results = manager.search_sessions(
            scope=scope,
            query=query,
            top_k=top_k,
            agent_name=agent_name or None,
            session_key=session_key or None,
            request_id=request_id or None,
        )
        if not results:
            return "No scoped session search results."
        lines = ["[SCOPED SESSION SEARCH RESULTS]"]
        for item in results:
            lines.append(
                f"- {item.created_at} session={item.session_key} "
                f"agent={item.agent_name} request={item.request_id}: {item.snippet}"
            )
        return "\n".join(lines)
