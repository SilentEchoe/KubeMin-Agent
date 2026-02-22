"""Main chat-agent loop."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .provider import OpenAICompatibleProvider
from .session import SessionManager
from .tools import ExecTool, ListDirTool, ReadFileTool, ToolRegistry, WriteFileTool


def build_default_tools(
    workspace: Path,
    exec_timeout_s: int = 30,
    restrict_to_workspace: bool = True,
) -> ToolRegistry:
    """Build default tool registry."""
    registry = ToolRegistry()
    registry.register(ReadFileTool(workspace=workspace, restrict_to_workspace=restrict_to_workspace))
    registry.register(WriteFileTool(workspace=workspace, restrict_to_workspace=restrict_to_workspace))
    registry.register(ListDirTool(workspace=workspace, restrict_to_workspace=restrict_to_workspace))
    registry.register(
        ExecTool(
            workspace=workspace,
            timeout_s=exec_timeout_s,
            restrict_to_workspace=restrict_to_workspace,
        )
    )
    return registry


class ChatAgent:
    """Tool-using chat agent inspired by nanobot."""

    def __init__(
        self,
        provider: OpenAICompatibleProvider,
        tools: ToolRegistry,
        sessions: SessionManager,
        workspace: Path,
        max_iterations: int = 12,
        history_limit: int = 30,
    ):
        self.provider = provider
        self.tools = tools
        self.sessions = sessions
        self.workspace = workspace.expanduser().resolve()
        self.max_iterations = max_iterations
        self.history_limit = history_limit

    async def process(self, user_message: str, session_key: str = "cli:default") -> str:
        session = self.sessions.get_or_create(session_key)
        messages = self._build_messages(session.get_history(self.history_limit), user_message)

        final_content: str | None = None
        for _ in range(self.max_iterations):
            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
            )
            if response.has_tool_calls:
                messages = self._add_assistant_with_tool_calls(messages, response.content, response.tool_calls)
                for tool_call in response.tool_calls:
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call.name,
                            "content": result,
                        }
                    )
            else:
                final_content = response.content or ""
                break

        if final_content is None:
            final_content = "I completed the request but did not generate a final response."

        session.add_message("user", user_message)
        session.add_message("assistant", final_content)
        self.sessions.save(session)
        return final_content

    def _build_messages(self, history: list[dict[str, Any]], user_message: str) -> list[dict[str, Any]]:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        system_prompt = (
            "You are KubeMin Agent, a practical assistant with tool access.\n"
            "Use tools when needed, otherwise answer directly.\n"
            "Be concise and factual.\n"
            f"Current time: {now}\n"
            f"Workspace: {self.workspace}\n"
            "Never claim to run actions you did not execute."
        )
        return [{"role": "system", "content": system_prompt}, *history, {"role": "user", "content": user_message}]

    @staticmethod
    def _add_assistant_with_tool_calls(messages: list[dict[str, Any]], content: str | None, tool_calls: Any) -> list[dict[str, Any]]:
        serialized = []
        for item in tool_calls:
            serialized.append(
                {
                    "id": item.id,
                    "type": "function",
                    "function": {
                        "name": item.name,
                        "arguments": json.dumps(item.arguments, ensure_ascii=False),
                    },
                }
            )
        messages.append(
            {
                "role": "assistant",
                "content": content or "",
                "tool_calls": serialized,
            }
        )
        return messages

