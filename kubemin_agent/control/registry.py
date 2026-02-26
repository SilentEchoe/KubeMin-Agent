"""Sub-Agent registry for managing agent lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from kubemin_agent.agents.base import BaseAgent


@dataclass
class AgentInfo:
    """Metadata about a registered sub-agent."""

    name: str
    description: str
    tools: list[str]
    status: str = "ready"


class AgentRegistry:
    """
    Central registry for sub-agent management.

    Handles registration, discovery, health status, and capability
    descriptions for all managed sub-agents.
    """

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        """Register a sub-agent."""
        self._agents[agent.name] = agent
        logger.info(f"Sub-agent registered: {agent.name} - {agent.description}")

    def unregister(self, name: str) -> None:
        """Unregister a sub-agent."""
        if name in self._agents:
            del self._agents[name]
            logger.info(f"Sub-agent unregistered: {name}")

    def get(self, name: str) -> BaseAgent | None:
        """Get a sub-agent by name."""
        return self._agents.get(name)

    def list_agents(self) -> list[AgentInfo]:
        """
        List all registered sub-agents with their capabilities.

        Used by the Scheduler for routing decisions.
        """
        return [
            AgentInfo(
                name=agent.name,
                description=agent.description,
                tools=agent.tools.tool_names,
            )
            for agent in self._agents.values()
        ]

    def get_routing_context(self) -> str:
        """
        Build a description of available agents for the Scheduler's LLM prompt.

        Returns:
            Formatted string describing each agent's capabilities.
        """
        lines: list[str] = []
        for agent in self._agents.values():
            tools_str = ", ".join(agent.tools.tool_names) if agent.tools.tool_names else "none"
            lines.append(f"- {agent.name}: {agent.description} (tools: {tools_str})")
        return "\n".join(lines)

    def health_check(self) -> dict[str, str]:
        """Check the health status of all registered sub-agents."""
        return {agent.name: "ready" for agent in self._agents.values()}

    @property
    def agent_names(self) -> list[str]:
        """Get list of registered agent names."""
        return list(self._agents.keys())

    def __len__(self) -> int:
        return len(self._agents)

    def __contains__(self, name: str) -> bool:
        return name in self._agents
