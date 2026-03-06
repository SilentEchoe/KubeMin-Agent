"""OrchestratorAgent — unified top-level agent with LLM-driven tool orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from kubemin_agent.agent.tools.delegate import DelegateAgentTool
from kubemin_agent.agent.tools.filesystem import ReadFileTool, WriteFileTool
from kubemin_agent.agent.tools.kubectl import KubectlTool
from kubemin_agent.agent.tools.shell import ShellTool
from kubemin_agent.agent.tools.yaml_validator import YAMLValidatorTool
from kubemin_agent.agents.base import BaseAgent
from kubemin_agent.providers.base import LLMProvider
from kubemin_agent.session.manager import SessionManager


class OrchestratorAgent(BaseAgent):
    """
    Unified orchestrator agent with progressive context management.

    Instead of routing through intent classification, this agent has direct
    access to ALL tools plus delegate tools for specialist sub-agents.
    The LLM autonomously decides whether to use tools directly or delegate
    to a specialist agent.
    """

    def __init__(
        self,
        provider: LLMProvider,
        sessions: SessionManager,
        delegate_tools: list[DelegateAgentTool] | None = None,
        **kwargs: Any,
    ) -> None:
        self._delegate_tools = delegate_tools or []
        super().__init__(provider, sessions, **kwargs)

    @property
    def name(self) -> str:
        return "orchestrator"

    @property
    def description(self) -> str:
        return (
            "Top-level orchestrator agent that can handle any task directly using "
            "built-in tools, or delegate to specialist agents for domain-specific work."
        )

    @property
    def system_prompt(self) -> str:
        # Build delegate agent descriptions for the prompt
        delegate_section = self._build_delegate_section()

        return (
            "You are the KubeMin-Agent Orchestrator, an intelligent assistant for "
            "cloud-native application management.\n\n"
            "## Your Capabilities\n\n"
            "You have two categories of tools:\n\n"
            "### 1. Direct Tools\n"
            "These let you perform actions immediately:\n"
            "- **read_file** / **write_file**: Read and write files in the workspace\n"
            "- **run_command**: Execute shell commands safely\n"
            "- **kubectl**: Query Kubernetes resources (read-only)\n"
            "- **validate_yaml**: Validate YAML syntax and structure\n\n"
            "### 2. Delegate Tools (Specialist Agents)\n"
            "These delegate a task to a domain-expert agent who has specialized "
            "knowledge and prompts. Use delegation when the task benefits from "
            "deep domain expertise or requires a multi-step specialist workflow.\n\n"
            f"{delegate_section}\n"
            "## Decision Guidelines\n\n"
            "- **Simple tasks** (file read/write, quick commands, simple queries): "
            "Use direct tools.\n"
            "- **Domain-specific complex tasks** (K8s diagnosis, workflow generation, "
            "platform patrol): Delegate to the specialist agent.\n"
            "- **Multi-domain tasks**: Combine direct tools and delegations as needed. "
            "You can call multiple tools in sequence.\n"
            "- **General questions**: Answer directly from your knowledge without tools.\n\n"
            "## Safety Constraints\n\n"
            "- File operations should stay within the workspace directory.\n"
            "- Shell commands must avoid destructive operations.\n"
            "- Kubernetes operations are read-only.\n"
            "- Never expose API keys, tokens, or credentials.\n\n"
            "Be helpful, concise, and always explain what you're doing."
        )

    @property
    def allowed_tools(self) -> list[str]:
        # No restrictions — orchestrator can use all registered tools.
        # Return None-ish signal by collecting all tools dynamically.
        return list(self.tools._tools.keys()) if self.tools else []

    def _register_tools(self) -> None:
        """Register direct tools and delegate tools."""
        # Direct tools
        self.tools.register(ReadFileTool(self._workspace))
        self.tools.register(WriteFileTool(self._workspace))
        self.tools.register(ShellTool())
        self.tools.register(KubectlTool())
        self.tools.register(YAMLValidatorTool())

        # Delegate tools (injected via constructor)
        for dtool in self._delegate_tools:
            self.tools.register(dtool)

    def _build_delegate_section(self) -> str:
        """Build the delegate tools description for the system prompt."""
        if not self._delegate_tools:
            return "(No specialist agents available)\n"

        lines: list[str] = []
        for dtool in self._delegate_tools:
            lines.append(f"- **{dtool.name}**: {dtool.description}")
        return "\n".join(lines) + "\n"

    def update_delegate_context(self, session_key: str, request_id: str) -> None:
        """Update session context on all delegate tools for the current request."""
        for dtool in self._delegate_tools:
            dtool.update_context(session_key, request_id)

    async def run(
        self,
        message: str,
        session_key: str,
        request_id: str = "",
        context_envelope: Any | None = None,
    ) -> str:
        """Execute with delegate context update."""
        self.update_delegate_context(session_key, request_id)
        return await super().run(
            message,
            session_key,
            request_id=request_id,
            context_envelope=context_envelope,
        )
