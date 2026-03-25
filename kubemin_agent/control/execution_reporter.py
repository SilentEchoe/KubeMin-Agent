"""Final execution report synthesis for scheduler plans."""

from __future__ import annotations

from loguru import logger

from kubemin_agent.control.scheduler_types import TaskExecutionResult
from kubemin_agent.providers.base import LLMProvider


class ExecutionReporter:
    """Generate end-user execution reports from task results."""

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def build_raw_results_prompt(
        self,
        *,
        original_message: str,
        execution_order: list[str],
        results: dict[str, TaskExecutionResult],
        remaining_task_ids: list[str],
        stopped_by_fail_fast: bool,
    ) -> str:
        """Compose a raw result document for final report generation."""
        raw_results_prompt = f"Original Objective: {original_message}\n\nTask Results:\n"

        for task_id in execution_order:
            if task_id not in results:
                continue
            result = results[task_id]
            status = "FAILED" if result.failed else "SUCCESS"
            raw_results_prompt += (
                f"--- Task {task_id} ({result.agent_name}) [{status}] ---\n"
                f"{result.content}\n\n"
            )

        if stopped_by_fail_fast and remaining_task_ids:
            skipped = ", ".join(sorted(remaining_task_ids))
            raw_results_prompt += f"--- Skipped Tasks ---\n{skipped} (due to fail_fast)\n\n"

        return raw_results_prompt

    async def generate_final_report(
        self,
        *,
        original_message: str,
        execution_order: list[str],
        results: dict[str, TaskExecutionResult],
        remaining_task_ids: list[str],
        stopped_by_fail_fast: bool,
    ) -> str:
        """Generate the final user-facing report via LLM."""
        raw_results_prompt = self.build_raw_results_prompt(
            original_message=original_message,
            execution_order=execution_order,
            results=results,
            remaining_task_ids=remaining_task_ids,
            stopped_by_fail_fast=stopped_by_fail_fast,
        )
        system_prompt = (
            "You are a technical report writer for KubeMin-Agent.\n"
            "Your job is to read the raw results of a multi-step execution plan and synthesize "
            "a single, cohesive, highly readable Markdown report for the user.\n"
            "Rules:\n"
            "- Start with a clear # Execution Report header.\n"
            "- Summarize the overall outcome.\n"
            "- Do not just blind-copy all raw logs; extract the most important findings/metrics/results.\n"
            "- Highlight any failures or warnings.\n"
            "- Keep a professional and objective tone."
        )

        try:
            report_response = await self.provider.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": raw_results_prompt},
                ]
            )
            return report_response.content or "Error generating report."
        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to generate final report via LLM: {e}")
            return (
                "Error: Plan completed but final report generation failed.\n\n"
                "Raw Results Preview:\n"
                + raw_results_prompt[:1000]
            )
