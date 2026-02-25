"""GeneralAgent - General-purpose task handler."""

from kubemin_agent.agents.base import BaseAgent


class GeneralAgent(BaseAgent):
    """
    General-purpose sub-agent.

    Handles file operations, shell commands, web searches,
    and any tasks not covered by specialized agents.
    Acts as the fallback agent.
    """

    @property
    def name(self) -> str:
        return "general"

    @property
    def description(self) -> str:
        return (
            "Handles general tasks including file operations, shell command execution, "
            "web searches, information retrieval, and general Q&A. "
            "Acts as a fallback for tasks not matched by specialized agents."
        )

    @property
    def system_prompt(self) -> str:
        return (
            "You are GeneralAgent, a versatile assistant within KubeMin-Agent.\n\n"
            "Your capabilities:\n"
            "- Read, write, and edit files\n"
            "- Execute shell commands safely\n"
            "- Search the web and fetch web pages\n"
            "- Answer general questions about cloud-native technologies\n"
            "- Perform miscellaneous tasks\n\n"
            "Safety constraints:\n"
            "- File operations should be within the workspace directory\n"
            "- Shell commands must avoid destructive operations\n"
            "- Never expose API keys or credentials\n\n"
            "Be helpful, concise, and always explain what you're doing."
        )

    def _register_tools(self) -> None:
        """Register general-purpose tools."""
        # Tools will be registered when concrete tool implementations are available
        # e.g., self.tools.register(FilesystemTool(...))
        # e.g., self.tools.register(ShellTool(...))
        # e.g., self.tools.register(WebSearchTool(...))
        pass
