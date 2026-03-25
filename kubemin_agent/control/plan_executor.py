"""Plan execution logic extracted from Scheduler."""

from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any

from loguru import logger

from kubemin_agent.control.agent_context import AgentContextStore, ContextEnvelope
from kubemin_agent.control.audit import AuditLog
from kubemin_agent.control.evaluation import ExecutionEvaluator
from kubemin_agent.control.execution_reporter import ExecutionReporter
from kubemin_agent.control.registry import AgentRegistry
from kubemin_agent.control.scheduler_types import DispatchPlan, SubTask, TaskExecutionResult
from kubemin_agent.control.validator import Validator
from kubemin_agent.providers.base import LLMProvider
from kubemin_agent.session.manager import SessionManager


class PlanExecutor:
    """Execute dispatch plans with validation/audit/evaluation semantics."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        registry: AgentRegistry,
        validator: Validator,
        audit: AuditLog,
        sessions: SessionManager,
        evaluator: ExecutionEvaluator | None = None,
        trace_capture: bool = True,
        max_trace_steps: int = 50,
        max_parallelism: int = 4,
        fail_fast: bool = False,
        reporter: ExecutionReporter | None = None,
    ) -> None:
        self.provider = provider
        self.registry = registry
        self.validator = validator
        self.audit = audit
        self.sessions = sessions
        self.evaluator = evaluator
        self.trace_capture = trace_capture
        self.max_trace_steps = max(1, max_trace_steps)
        self.max_parallelism = max(1, max_parallelism)
        self.fail_fast = fail_fast
        self.reporter = reporter or ExecutionReporter(provider)

    async def execute_plan(
        self,
        *,
        plan: DispatchPlan,
        original_message: str,
        session_key: str,
        request_id: str,
    ) -> str:
        """
        Execute a dispatch plan.

        Args:
            plan: The dispatch plan.
            original_message: The original user message.
            session_key: Session identifier.
            request_id: Correlation ID for logs.

        Returns:
            Combined result from all task executions.
        """
        if not plan.tasks:
            return "Error: Dispatch plan is empty"

        self.sessions.init_active_plan_doc(session_key, original_message, plan.tasks)

        index_map = {task.task_id: idx for idx, task in enumerate(plan.tasks)}
        remaining = {task.task_id: task for task in plan.tasks}
        completed: set[str] = set()
        results: dict[str, TaskExecutionResult] = {}
        execution_order: list[str] = []
        context_store = AgentContextStore()
        stopped_by_fail_fast = False

        while remaining:
            ready = [
                task
                for task in remaining.values()
                if all(dep in completed for dep in task.depends_on)
            ]
            ready.sort(key=lambda task: index_map.get(task.task_id, 0))

            if not ready:
                unresolved = ", ".join(sorted(remaining.keys()))
                message = (
                    "Error: Task dependency cycle or unresolved dependency detected: "
                    f"{unresolved}"
                )
                for task_id in list(remaining.keys()):
                    results[task_id] = TaskExecutionResult(
                        task_id=task_id,
                        content=message,
                        failed=True,
                    )
                    execution_order.append(task_id)
                break

            if plan.execution_mode == "parallel":
                failed_in_round = await self._execute_parallel_round(
                    ready=ready,
                    remaining=remaining,
                    completed=completed,
                    results=results,
                    execution_order=execution_order,
                    context_store=context_store,
                    original_message=original_message,
                    session_key=session_key,
                    request_id=request_id,
                )
                if self.fail_fast and failed_in_round:
                    stopped_by_fail_fast = True
                    break
                continue

            task = ready[0]
            self.sessions.update_active_plan_task_status(session_key, task.task_id, "[-]")

            plan_path = self.sessions.get_active_plan_doc_path(session_key)
            active_plan_text = plan_path.read_text(encoding="utf-8") if plan_path else ""

            context_envelope = context_store.build_envelope(
                task_id=task.task_id,
                agent_name=task.agent_name,
                task_description=task.description,
                original_message=original_message,
                depends_on=task.depends_on,
                active_plan_content=active_plan_text,
            )
            task_result = await self._execute_task(
                task=task,
                original_message=original_message,
                session_key=session_key,
                request_id=request_id,
                context_envelope=context_envelope,
            )
            results[task.task_id] = task_result
            execution_order.append(task.task_id)
            remaining.pop(task.task_id, None)
            completed.add(task.task_id)

            summary_text = context_store._summarize_result(task_result.content)
            self.sessions.update_active_plan_task_status(
                session_key, task.task_id, "[x]", summary_text
            )

            context_store.add_result(
                task_id=task.task_id,
                agent_name=task_result.agent_name or task.agent_name,
                result=task_result.content,
            )

            if self.fail_fast and task_result.failed:
                stopped_by_fail_fast = True
                break

        return await self.reporter.generate_final_report(
            original_message=original_message,
            execution_order=execution_order,
            results=results,
            remaining_task_ids=list(remaining.keys()),
            stopped_by_fail_fast=stopped_by_fail_fast,
        )

    async def _execute_parallel_round(
        self,
        *,
        ready: list[SubTask],
        remaining: dict[str, SubTask],
        completed: set[str],
        results: dict[str, TaskExecutionResult],
        execution_order: list[str],
        context_store: AgentContextStore,
        original_message: str,
        session_key: str,
        request_id: str,
    ) -> bool:
        """Execute one dependency-resolved round in parallel."""
        failed_in_round = False

        for i in range(0, len(ready), self.max_parallelism):
            chunk = ready[i : i + self.max_parallelism]

            plan_path = self.sessions.get_active_plan_doc_path(session_key)
            active_plan_text = plan_path.read_text(encoding="utf-8") if plan_path else ""

            for task in chunk:
                self.sessions.update_active_plan_task_status(session_key, task.task_id, "[-]")

            envelopes = {
                task.task_id: context_store.build_envelope(
                    task_id=task.task_id,
                    agent_name=task.agent_name,
                    task_description=task.description,
                    original_message=original_message,
                    depends_on=task.depends_on,
                    active_plan_content=active_plan_text,
                )
                for task in chunk
            }
            chunk_results = await asyncio.gather(
                *[
                    self._execute_task(
                        task=task,
                        original_message=original_message,
                        session_key=session_key,
                        request_id=request_id,
                        context_envelope=envelopes.get(task.task_id),
                    )
                    for task in chunk
                ]
            )

            for task, task_result in zip(chunk, chunk_results, strict=True):
                results[task.task_id] = task_result
                execution_order.append(task.task_id)
                remaining.pop(task.task_id, None)
                completed.add(task.task_id)

                summary_text = context_store._summarize_result(task_result.content)
                self.sessions.update_active_plan_task_status(
                    session_key, task.task_id, "[x]", summary_text
                )

                context_store.add_result(
                    task_id=task.task_id,
                    agent_name=task_result.agent_name or task.agent_name,
                    result=task_result.content,
                )
                failed_in_round = failed_in_round or task_result.failed

            if self.fail_fast and failed_in_round:
                return True

        return failed_in_round

    async def _execute_task(
        self,
        *,
        task: SubTask,
        original_message: str,
        session_key: str,
        request_id: str,
        context_envelope: ContextEnvelope | None = None,
    ) -> TaskExecutionResult:
        """Execute one task with logging and validation."""
        agent = self.registry.get(task.agent_name)
        if not agent:
            logger.warning(f"Agent '{task.agent_name}' not found, trying 'general'")
            agent = self.registry.get("general")
            if not agent:
                return TaskExecutionResult(
                    task_id=task.task_id,
                    content=f"Error: No agent available for task: {task.description}",
                    agent_name=task.agent_name,
                    failed=True,
                )

        self.audit.log_dispatch(
            session_key=session_key,
            message=original_message,
            agent_name=agent.name,
            task_description=task.description,
            task_id=task.task_id,
            request_id=request_id,
        )

        start_time = time.monotonic()
        failed = False
        self._prepare_agent_trace(agent=agent, task_id=task.task_id)

        try:
            result = await self._run_agent(
                agent=agent,
                task_description=task.description,
                session_key=session_key,
                request_id=request_id,
                context_envelope=context_envelope,
            )
            duration_ms = (time.monotonic() - start_time) * 1000
            self.audit.log_execution(
                session_key=session_key,
                agent_name=agent.name,
                result_preview=result,
                duration_ms=duration_ms,
                task_id=task.task_id,
                success=True,
                request_id=request_id,
            )
        except Exception as e:  # noqa: BLE001
            duration_ms = (time.monotonic() - start_time) * 1000
            result = f"Error from {agent.name}: {e}"
            failed = True
            self.audit.log_execution(
                session_key=session_key,
                agent_name=agent.name,
                result_preview=result,
                duration_ms=duration_ms,
                task_id=task.task_id,
                success=False,
                request_id=request_id,
            )
            logger.error(f"Agent execution failed: {agent.name} - {e}")

        trace_events = self._consume_agent_trace(agent)

        validation = await self.validator.validate(
            agent_name=agent.name,
            result=result,
            context={"session_key": session_key, "request_id": request_id},
        )

        sanitized = validation.sanitized_result or result
        self.audit.log_validation(
            session_key=session_key,
            agent_name=agent.name,
            passed=validation.passed,
            task_id=task.task_id,
            reason=validation.reason,
            request_id=request_id,
            severity=validation.severity,
            policy_id=validation.policy_id,
            redactions=validation.redactions,
        )

        await self._evaluate_task(
            agent=agent,
            task=task,
            session_key=session_key,
            request_id=request_id,
            final_output=sanitized,
            trace_events=trace_events,
            validation=validation,
        )

        if not validation.passed:
            if validation.severity == "block":
                return TaskExecutionResult(
                    task_id=task.task_id,
                    content=f"[Validation Blocked] {validation.reason}\n\n{sanitized}",
                    agent_name=agent.name,
                    failed=True,
                )

            sanitized = f"[Validation Warning] {validation.reason}\n\n{sanitized}"

        return TaskExecutionResult(
            task_id=task.task_id,
            content=sanitized,
            agent_name=agent.name,
            failed=failed,
        )

    def _prepare_agent_trace(self, agent: Any, task_id: str) -> None:
        """Inject trace context/config into agents that support it."""
        set_trace_context = getattr(agent, "set_trace_context", None)
        if callable(set_trace_context):
            set_trace_context(task_id=task_id)

        set_trace_capture = getattr(agent, "set_trace_capture", None)
        if callable(set_trace_capture):
            set_trace_capture(enabled=self.trace_capture, max_steps=self.max_trace_steps)

    async def _run_agent(
        self,
        *,
        agent: Any,
        task_description: str,
        session_key: str,
        request_id: str,
        context_envelope: ContextEnvelope | None,
    ) -> str:
        """Run an agent while keeping backward compatibility for run signatures."""
        run_callable = getattr(agent, "run")
        supports_context_envelope = False
        try:
            params = inspect.signature(run_callable).parameters
            supports_context_envelope = "context_envelope" in params
        except (TypeError, ValueError):
            supports_context_envelope = False

        if supports_context_envelope:
            return await run_callable(  # type: ignore[misc]
                task_description,
                session_key,
                request_id=request_id,
                context_envelope=context_envelope,
            )

        return await run_callable(  # type: ignore[misc]
            task_description,
            session_key,
            request_id=request_id,
        )

    def _consume_agent_trace(self, agent: Any) -> list[dict[str, Any]]:
        """Collect and clear latest trace events from agent when available."""
        consume_trace_events = getattr(agent, "consume_trace_events", None)
        if callable(consume_trace_events):
            try:
                events = consume_trace_events()
                if isinstance(events, list):
                    return events
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Failed to consume agent trace events: {e}")
        return []

    async def _evaluate_task(
        self,
        *,
        agent: Any,
        task: SubTask,
        session_key: str,
        request_id: str,
        final_output: str,
        trace_events: list[dict[str, Any]],
        validation: Any,
    ) -> None:
        """Evaluate task execution and write evaluation audit logs."""
        if not self.evaluator:
            return

        try:
            evaluation = await self.evaluator.evaluate(
                agent_name=agent.name,
                task_description=task.description,
                final_output=final_output,
                trace_events=trace_events,
                validation=validation,
            )
            self.audit.log_evaluation(
                session_key=session_key,
                agent_name=agent.name,
                task_id=task.task_id,
                overall_score=evaluation.overall_score,
                dimension_scores=evaluation.dimension_scores,
                passed=evaluation.passed,
                warn_threshold=evaluation.warn_threshold,
                reasons=evaluation.reasons,
                suggestions=evaluation.suggestions,
                request_id=request_id,
            )
            if not evaluation.passed:
                logger.warning(
                    f"Evaluation warning: agent={agent.name}, task={task.task_id}, "
                    f"score={evaluation.overall_score}/{evaluation.warn_threshold}"
                )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Task evaluation failed for agent={getattr(agent, 'name', '?')}: {e}")
