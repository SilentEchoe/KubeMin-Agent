"""Context builder for assembling agent prompts."""

from datetime import datetime
from pathlib import Path
from typing import Any

from kubemin_agent.agent.memory import MemoryStore
from kubemin_agent.agent.skills import SkillsLoader


class ContextBuilder:
    """
    Builds the context (system prompt + messages) for the agent.

    Assembles bootstrap files, memory, skills, and conversation history
    into a coherent prompt for the LLM.
    """

    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md"]

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.memory = MemoryStore.create(workspace)
        self.skills = SkillsLoader(workspace)

    def build_system_prompt(self, skill_names: list[str] | None = None) -> str:
        """
        Build the system prompt from bootstrap files, memory, and skills.

        Args:
            skill_names: Optional list of skills to include.

        Returns:
            Complete system prompt.
        """
        parts: list[str] = []

        # Core identity
        parts.append(self._get_identity())

        # Bootstrap files
        bootstrap = self._load_bootstrap_files()
        if bootstrap:
            parts.append(bootstrap)

        # Memory context (non-async fallback: load all, capped)
        memory = self._get_memory_sync()
        if memory:
            parts.append(f"# Memory\n\n{memory}")

        # Skills - progressive loading
        # 1. Always-loaded skills: include full content
        always_skills = self.skills.get_always_skills()
        if always_skills:
            always_content = self.skills.load_skills_for_context(always_skills)
            if always_content:
                parts.append(f"# Active Skills\n\n{always_content}")

        # 2. Available skills: only show summary (agent uses read_file to load)
        skills_summary = self.skills.build_skills_summary()
        if skills_summary:
            parts.append(
                "# Skills\n\n"
                "The following skills extend your capabilities. "
                "To use a skill, read its SKILL.md file using the read_file tool.\n\n"
                f"{skills_summary}"
            )

        return "\n\n---\n\n".join(parts)

    def _get_identity(self) -> str:
        """Get the core identity section."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        workspace_path = str(self.workspace.expanduser().resolve())

        return (
            "# KubeMin-Agent\n\n"
            "You are KubeMin-Agent, an intelligent assistant for cloud-native application management. "
            "You have access to tools that allow you to:\n"
            "- Read, write, and edit files\n"
            "- Execute shell commands\n"
            "- Query Kubernetes resources\n"
            "- Interact with KubeMin platform APIs\n"
            "- Search the web and fetch web pages\n\n"
            f"## Current Time\n{now}\n\n"
            f"## Workspace\nYour workspace is at: {workspace_path}\n"
            f"- Memory files: {workspace_path}/memory/MEMORY.md\n"
            f"- Daily notes: {workspace_path}/memory/YYYY-MM-DD.md\n"
            f"- Custom skills: {workspace_path}/skills/{{skill-name}}/SKILL.md\n\n"
            "Always be helpful, accurate, and concise. When using tools, explain what you're doing."
        )

    def _get_memory_sync(self) -> str:
        """Get memory context synchronously (for use in sync build_system_prompt)."""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            # Already in an async context -- schedule as a task
            # Fall back to empty; async callers should use memory.get_context() directly
            return ""
        except RuntimeError:
            pass

        # No running loop -- safe to run synchronously
        try:
            return asyncio.run(self.memory.get_context())
        except Exception:
            return ""

    def _load_bootstrap_files(self) -> str:
        """Load all bootstrap files from workspace."""
        parts: list[str] = []

        for filename in self.BOOTSTRAP_FILES:
            file_path = self.workspace / filename
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                parts.append(f"## {filename}\n\n{content}")

        return "\n\n".join(parts) if parts else ""

    def build_messages(
        self,
        history: list[dict[str, Any]],
        current_message: str,
        skill_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Build the complete message list for an LLM call.

        Args:
            history: Previous conversation messages.
            current_message: The new user message.
            skill_names: Optional skills to include.

        Returns:
            List of messages including system prompt.
        """
        messages: list[dict[str, Any]] = []

        # System prompt
        system_prompt = self.build_system_prompt(skill_names)
        messages.append({"role": "system", "content": system_prompt})

        # History
        messages.extend(history)

        # Current message
        messages.append({"role": "user", "content": current_message})

        return messages

    def add_tool_result(
        self,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        tool_name: str,
        result: str,
    ) -> list[dict[str, Any]]:
        """
        Add a tool result to the message list.

        Args:
            messages: Current message list.
            tool_call_id: ID of the tool call.
            tool_name: Name of the tool.
            result: Tool execution result.

        Returns:
            Updated message list.
        """
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": tool_name,
                "content": result,
            }
        )
        return messages

    def add_assistant_message(
        self,
        messages: list[dict[str, Any]],
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Add an assistant message to the message list.

        Args:
            messages: Current message list.
            content: Message content.
            tool_calls: Optional tool calls.

        Returns:
            Updated message list.
        """
        msg: dict[str, Any] = {"role": "assistant", "content": content or ""}

        if tool_calls:
            msg["tool_calls"] = tool_calls

        messages.append(msg)
        return messages
