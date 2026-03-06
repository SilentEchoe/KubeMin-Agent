"""DelegateAgentTool — wrap sub-agents as callable tools for LLM orchestration."""

from __future__ import annotations

from typing import Any

from loguru import logger

from kubemin_agent.agent.tools.base import Tool


class DelegateAgentTool(Tool):
    """
    Wraps a sub-agent as a standard Tool so the LLM can delegate tasks
    to domain-expert agents autonomously.

    The LLM sees this as a regular tool with a ``task`` parameter.
    Under the hood it calls ``agent.run(task, session_key)``.
    """

    def __init__(
        self,
        agent: Any,
        session_key: str = "",
        request_id: str = "",
    ) -> None:
        self._agent = agent
        self._session_key = session_key
        self._request_id = request_id

    # ------------------------------------------------------------------
    # Tool interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return f"delegate_{self._agent.name}"

    @property
    def description(self) -> str:
        return (
            f"Delegate a task to the {self._agent.name} specialist agent. "
            f"Capability: {self._agent.description} "
            f"Use this when the task requires domain expertise that this agent provides."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "A clear, actionable task description for the specialist agent. "
                        "Be specific about what information you need or what action to perform."
                    ),
                },
            },
            "required": ["task"],
        }

    async def execute(self, **kwargs: Any) -> str:
        task = kwargs.get("task", "")
        if not task:
            return "Error: 'task' parameter is required and must not be empty."

        agent_name = self._agent.name
        logger.info(f"[DelegateAgentTool] Delegating to {agent_name}: {task[:120]}")

        try:
            result = await self._agent.run(
                task,
                self._session_key,
                request_id=self._request_id,
            )
            return result or "(Agent returned empty response)"
        except Exception as e:  # noqa: BLE001
            logger.error(f"[DelegateAgentTool] {agent_name} execution failed: {e}")
            return f"Error: Delegation to {agent_name} failed — {e}"

    # ------------------------------------------------------------------
    # Runtime context update
    # ------------------------------------------------------------------

    def update_context(self, session_key: str, request_id: str) -> None:
        """Update runtime context (called by scheduler per-request)."""
        self._session_key = session_key
        self._request_id = request_id


def create_delegate_tools(
    registry: Any,
    session_key: str = "",
    request_id: str = "",
    exclude: set[str] | None = None,
) -> list[DelegateAgentTool]:
    """
    Create DelegateAgentTool instances for all agents in the registry.

    Args:
        registry: AgentRegistry instance.
        session_key: Default session key for delegate calls.
        request_id: Default request ID for delegate calls.
        exclude: Agent names to skip (e.g. the orchestrator itself).

    Returns:
        List of DelegateAgentTool instances.
    """
    exclude = exclude or set()
    tools: list[DelegateAgentTool] = []

    for info in registry.list_agents():
        if info.name in exclude:
            continue
        agent = registry.get(info.name)
        if agent is None:
            continue
        tools.append(
            DelegateAgentTool(
                agent=agent,
                session_key=session_key,
                request_id=request_id,
            )
        )

    return tools
