"""WorkflowAgent - KubeMin workflow orchestration specialist."""

from kubemin_agent.agents.base import BaseAgent


class WorkflowAgent(BaseAgent):
    """
    Workflow orchestration sub-agent.

    Handles workflow generation, optimization, validation,
    execution monitoring, and failure analysis.
    """

    @property
    def name(self) -> str:
        return "workflow"

    @property
    def description(self) -> str:
        return (
            "Handles KubeMin workflow tasks including workflow generation, "
            "step optimization, YAML validation, execution monitoring, "
            "and failure root cause analysis."
        )

    @property
    def system_prompt(self) -> str:
        return (
            "You are WorkflowAgent, a KubeMin Workflow orchestration specialist.\n\n"
            "Your expertise:\n"
            "- Generate workflow YAML definitions from natural language descriptions\n"
            "- Optimize workflow step ordering and dependencies\n"
            "- Validate workflow configurations for correctness\n"
            "- Monitor workflow execution and explain status\n"
            "- Analyze workflow failures and suggest fixes\n\n"
            "When generating workflows:\n"
            "- Follow KubeMin workflow specification strictly\n"
            "- Include proper step dependencies\n"
            "- Add appropriate resource limits and health checks\n"
            "- Consider trait configurations (scaling, ingress, etc.)\n\n"
            "Always provide clear explanations alongside generated YAML."
        )

    def _register_tools(self) -> None:
        """Register workflow-specific tools."""
        # Tools will be registered when concrete tool implementations are available
        # e.g., self.tools.register(WorkflowCRUDTool(...))
        # e.g., self.tools.register(WorkflowValidateTool(...))
        pass
