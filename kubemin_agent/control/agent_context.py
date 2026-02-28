"""Cross-agent context envelope for multi-step scheduling."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ContextFinding:
    """Structured finding from one completed task."""

    source_task_id: str
    agent_name: str
    summary: str


@dataclass
class ContextEnvelope:
    """Context passed from scheduler to an agent before task execution."""

    task_id: str
    agent_name: str
    task_description: str
    original_message: str
    dependency_findings: list[ContextFinding] = field(default_factory=list)
    global_findings: list[ContextFinding] = field(default_factory=list)

    def to_system_prompt(self, max_chars: int = 1400) -> str:
        """Render envelope into compact prompt text."""
        lines: list[str] = [
            "[SHARED TASK CONTEXT]",
            f"Current task: {self.task_description}",
            f"Original request: {self.original_message[:260]}",
        ]

        if self.dependency_findings:
            lines.append("Dependency findings:")
            for finding in self.dependency_findings:
                lines.append(
                    f"- {finding.source_task_id} ({finding.agent_name}): {finding.summary}"
                )

        if self.global_findings:
            lines.append("Recent findings:")
            for finding in self.global_findings:
                lines.append(
                    f"- {finding.source_task_id} ({finding.agent_name}): {finding.summary}"
                )

        lines.append("Use shared findings to avoid repeating already completed exploration.")

        text = "\n".join(lines)
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + f" ...[truncated {len(text) - max_chars} chars]"


class AgentContextStore:
    """In-memory store for sharing concise results across scheduled tasks."""

    def __init__(
        self,
        max_tasks: int = 20,
        finding_max_chars: int = 240,
        recent_global_limit: int = 2,
    ) -> None:
        self._max_tasks = max(1, max_tasks)
        self._finding_max_chars = max(80, finding_max_chars)
        self._recent_global_limit = max(0, recent_global_limit)
        self._findings: dict[str, ContextFinding] = {}
        self._order: list[str] = []

    def add_result(self, task_id: str, agent_name: str, result: str) -> None:
        """Store a concise finding for a completed task."""
        finding = ContextFinding(
            source_task_id=task_id,
            agent_name=agent_name,
            summary=self._summarize_result(result),
        )
        self._findings[task_id] = finding
        if task_id in self._order:
            self._order.remove(task_id)
        self._order.append(task_id)

        while len(self._order) > self._max_tasks:
            old = self._order.pop(0)
            self._findings.pop(old, None)

    def build_envelope(
        self,
        *,
        task_id: str,
        agent_name: str,
        task_description: str,
        original_message: str,
        depends_on: list[str],
    ) -> ContextEnvelope:
        """Build envelope for the current task from dependency and recent findings."""
        dependency_findings = [
            self._findings[dep]
            for dep in depends_on
            if dep in self._findings
        ]

        global_findings: list[ContextFinding] = []
        if self._recent_global_limit > 0:
            for source_task_id in reversed(self._order):
                if source_task_id in depends_on:
                    continue
                finding = self._findings.get(source_task_id)
                if not finding:
                    continue
                global_findings.append(finding)
                if len(global_findings) >= self._recent_global_limit:
                    break
            global_findings.reverse()

        return ContextEnvelope(
            task_id=task_id,
            agent_name=agent_name,
            task_description=task_description,
            original_message=original_message,
            dependency_findings=dependency_findings,
            global_findings=global_findings,
        )

    def _summarize_result(self, result: str) -> str:
        """Extract compact signal summary from task output text."""
        text = (result or "").strip()
        if not text:
            return "(empty result)"

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        signal_lines: list[str] = []
        for line in lines:
            lowered = line.lower()
            if any(
                token in lowered
                for token in ("error", "fail", "warning", "timeout", "blocked", "建议", "结论")
            ):
                signal_lines.append(line)
            if len(signal_lines) >= 3:
                break

        if signal_lines:
            summary = " | ".join(signal_lines)
        else:
            summary = lines[0] if lines else text

        if len(summary) <= self._finding_max_chars:
            return summary
        return summary[: self._finding_max_chars] + " ..."
