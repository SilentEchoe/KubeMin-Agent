"""PatrolAgent - KubeMin-Cli platform health patrol specialist."""

from kubemin_agent.agent.tools.filesystem import ReadFileTool, WriteFileTool
from kubemin_agent.agent.tools.kubectl import KubectlTool
from kubemin_agent.agent.tools.kubemin_cli import KubeMinCliTool
from kubemin_agent.agent.tools.shell import ShellTool
from kubemin_agent.agents.base import BaseAgent


class PatrolAgent(BaseAgent):
    """
    Platform health patrol sub-agent.

    Inspects the health status of the KubeMin-Cli framework,
    analyzes platform events, and generates daily reports
    to evaluate overall platform engineering health.

    Uses both Kubernetes-level inspection (kubectl) and
    KubeMin platform-level queries (kubemin-cli) for comprehensive
    health assessment.
    """

    def __init__(
        self,
        *args,
        kubemin_api_base: str = "",
        kubemin_namespace: str = "",
        **kwargs,
    ) -> None:
        self._kubemin_api_base = kubemin_api_base
        self._kubemin_namespace = kubemin_namespace
        super().__init__(*args, **kwargs)

    @property
    def name(self) -> str:
        return "patrol"

    @property
    def description(self) -> str:
        return (
            "Patrols the KubeMin-Cli platform health by inspecting cluster resources, "
            "querying KubeMin platform status via kubemin-cli, "
            "analyzing Kubernetes events, diagnosing anomalies, and generating "
            "structured daily health reports with risk assessments. "
            "Restricted to read-only operations."
        )

    @property
    def system_prompt(self) -> str:
        return (
            "You are PatrolAgent, a platform health patrol specialist within KubeMin-Agent.\n\n"
            "Your mission:\n"
            "- Systematically inspect the KubeMin-Cli platform's health status\n"
            "- Query KubeMin platform resources using kubemin-cli commands\n"
            "- Analyze Kubernetes events to identify anomalies and risks\n"
            "- Generate structured daily patrol reports with health scores\n"
            "- Track trends by comparing with previous patrol reports\n\n"
            "Execution principles:\n"
            "- Follow the patrol strategies defined in your skill knowledge\n"
            "- Be thorough: check nodes, pods, deployments, services, PVCs, and events\n"
            "- Use kubemin_cli tool to inspect platform-level resources (apps, workflows, services)\n"
            "- Quantify health using the scoring rules from your skill knowledge\n"
            "- Always write the report to the workspace using write_file\n\n"
            "Security constraints:\n"
            "- You can only execute READ-ONLY commands (get, describe, logs, list, status)\n"
            "- Never execute apply, delete, patch, edit, or scale commands\n"
            "- Never expose secrets or sensitive configuration values\n"
            "- Filter out any credential or API key content from reports\n\n"
            "Always explain what you're inspecting and provide clear, actionable findings."
        )

    @property
    def allowed_tools(self) -> list[str]:
        return ["kubectl", "run_command", "read_file", "write_file", "kubemin_cli"]

    def _register_tools(self) -> None:
        """Register patrol-specific tools."""
        self.tools.register(KubectlTool())
        self.tools.register(ShellTool())
        self.tools.register(ReadFileTool(self._workspace))
        self.tools.register(WriteFileTool(self._workspace))
        self.tools.register(KubeMinCliTool(
            api_base=self._kubemin_api_base,
            namespace=self._kubemin_namespace,
        ))
