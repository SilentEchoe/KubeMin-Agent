"""K8sAgent - Kubernetes operations specialist."""

from kubemin_agent.agent.tools.kubectl import KubectlTool
from kubemin_agent.agents.base import BaseAgent


class K8sAgent(BaseAgent):
    """
    Kubernetes operations sub-agent.

    Handles cluster queries, resource inspection, log viewing,
    and fault diagnosis within configured namespace boundaries.
    """

    @property
    def name(self) -> str:
        return "k8s"

    @property
    def description(self) -> str:
        return (
            "Handles Kubernetes cluster operations including resource queries, "
            "status diagnosis, log viewing, and pod inspection. "
            "Restricted to read-only operations within allowed namespaces."
        )

    @property
    def system_prompt(self) -> str:
        return (
            "You are K8sAgent, a Kubernetes operations specialist within KubeMin-Agent.\n\n"
            "Your expertise:\n"
            "- Query and inspect Kubernetes resources (pods, deployments, services, etc.)\n"
            "- Diagnose cluster and application issues\n"
            "- View container logs\n"
            "- Explain Kubernetes concepts and best practices\n\n"
            "Security constraints:\n"
            "- You can only execute READ-ONLY commands (get, describe, logs)\n"
            "- You must operate within the configured namespace\n"
            "- Never execute apply, delete, patch, edit, or scale commands\n"
            "- Never expose secrets or sensitive configuration values\n\n"
            "Always explain what you're doing and provide clear, actionable information."
        )

    @property
    def allowed_tools(self) -> list[str]:
        return ["kubectl"]

    def _register_tools(self) -> None:
        """Register K8s-specific tools."""
        self.tools.register(KubectlTool())
