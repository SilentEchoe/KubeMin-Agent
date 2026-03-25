"""Scheduler for intent analysis and task dispatch."""

from __future__ import annotations

import dataclasses
import time
import uuid
from typing import Any

from loguru import logger

from kubemin_agent.control.audit import AuditLog
from kubemin_agent.control.evaluation import ExecutionEvaluator
from kubemin_agent.control.execution_reporter import ExecutionReporter
from kubemin_agent.control.intent_planner import IntentPlanner
from kubemin_agent.control.plan_executor import PlanExecutor
from kubemin_agent.control.registry import AgentRegistry
from kubemin_agent.control.scheduler_types import DispatchPlan, SubTask, TaskExecutionResult
from kubemin_agent.control.validator import Validator
from kubemin_agent.providers.base import LLMProvider
from kubemin_agent.session.manager import SessionManager


class Scheduler:
    """
    Core scheduler for the control plane.

    Supports two orchestration modes:
    - ``orchestrated``: A single OrchestratorAgent with all tools + delegate
      tools decides autonomously how to fulfil the request (progressive context).
    - ``intent_dispatch``: Legacy mode — LLM classifies intent first, then
      dispatches to hardcoded sub-agents.
    """

    def __init__(
        self,
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
        orchestration_mode: str = "orchestrated",
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
        self.orchestration_mode = orchestration_mode
        self._orchestrator: Any | None = None

        self._intent_planner = IntentPlanner(provider=provider, registry=registry)
        self._execution_reporter = ExecutionReporter(provider=provider)
        self._plan_executor = PlanExecutor(
            provider=provider,
            registry=registry,
            validator=validator,
            audit=audit,
            sessions=sessions,
            evaluator=evaluator,
            trace_capture=trace_capture,
            max_trace_steps=max_trace_steps,
            max_parallelism=max_parallelism,
            fail_fast=fail_fast,
            reporter=self._execution_reporter,
        )

    def set_orchestrator(self, agent: Any) -> None:
        """Set the orchestrator agent for orchestrated mode."""
        self._orchestrator = agent

    async def dispatch(
        self,
        message: str,
        session_key: str,
        request_id: str | None = None,
        plan_mode: bool = False,
    ) -> str:
        """
        Main entry point: routes to orchestrated or intent_dispatch mode.

        Args:
            message: The user's message.
            session_key: Session identifier.
            request_id: Optional correlation ID for tracing.
            plan_mode: If True, generate and save the plan without executing it.

        Returns:
            The final response to send back to the user or the formatted plan.
        """
        if self.orchestration_mode == "orchestrated" and self._orchestrator and not plan_mode:
            return await self.dispatch_orchestrated(message, session_key, request_id)

        # intent_dispatch path (also used for plan_mode)
        return await self._dispatch_intent(message, session_key, request_id, plan_mode)

    async def dispatch_orchestrated(
        self,
        message: str,
        session_key: str,
        request_id: str | None = None,
    ) -> str:
        """
        Orchestrated dispatch: let the OrchestratorAgent handle everything.

        No intent classification — the LLM autonomously decides which tools
        or delegate agents to use.
        """
        dispatch_id = request_id or uuid.uuid4().hex[:12]

        self.audit.log_dispatch(
            session_key=session_key,
            message=message,
            agent_name="orchestrator",
            task_description=message,
            task_id="orchestrated",
            request_id=dispatch_id,
        )

        start_time = time.monotonic()
        self._prepare_agent_trace(agent=self._orchestrator, task_id="orchestrated")

        try:
            result = await self._orchestrator.run(
                message,
                session_key,
                request_id=dispatch_id,
            )
            duration_ms = (time.monotonic() - start_time) * 1000
            self.audit.log_execution(
                session_key=session_key,
                agent_name="orchestrator",
                result_preview=result,
                duration_ms=duration_ms,
                task_id="orchestrated",
                success=True,
                request_id=dispatch_id,
            )
        except Exception as e:  # noqa: BLE001
            duration_ms = (time.monotonic() - start_time) * 1000
            result = f"Error from orchestrator: {e}"
            self.audit.log_execution(
                session_key=session_key,
                agent_name="orchestrator",
                result_preview=result,
                duration_ms=duration_ms,
                task_id="orchestrated",
                success=False,
                request_id=dispatch_id,
            )
            logger.error(f"Orchestrator execution failed: {e}")

        trace_events = self._consume_agent_trace(self._orchestrator)

        validation = await self.validator.validate(
            agent_name="orchestrator",
            result=result,
            context={"session_key": session_key, "request_id": dispatch_id},
        )

        sanitized = validation.sanitized_result or result
        self.audit.log_validation(
            session_key=session_key,
            agent_name="orchestrator",
            passed=validation.passed,
            task_id="orchestrated",
            reason=validation.reason,
            request_id=dispatch_id,
            severity=validation.severity,
            policy_id=validation.policy_id,
            redactions=validation.redactions,
        )

        if self.evaluator:
            try:
                evaluation = await self.evaluator.evaluate(
                    agent_name="orchestrator",
                    task_description=message,
                    final_output=sanitized,
                    trace_events=trace_events,
                    validation=validation,
                )
                self.audit.log_evaluation(
                    session_key=session_key,
                    agent_name="orchestrator",
                    task_id="orchestrated",
                    overall_score=evaluation.overall_score,
                    dimension_scores=evaluation.dimension_scores,
                    passed=evaluation.passed,
                    warn_threshold=evaluation.warn_threshold,
                    reasons=evaluation.reasons,
                    suggestions=evaluation.suggestions,
                    request_id=dispatch_id,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Orchestrator evaluation failed: {e}")

        if not validation.passed and validation.severity == "block":
            sanitized = f"[Validation Blocked] {validation.reason}\n\n{sanitized}"

        self.sessions.save_turn(session_key, message, sanitized)
        return sanitized

    async def _dispatch_intent(
        self,
        message: str,
        session_key: str,
        request_id: str | None = None,
        plan_mode: bool = False,
    ) -> str:
        """
        Intent-dispatch flow: analyze intent -> select agent -> execute.
        """
        dispatch_id = request_id or uuid.uuid4().hex[:12]

        # 1. Analyze intent
        plan = await self.analyze_intent(message)

        if plan_mode:
            plan_data = {
                "tasks": [dataclasses.asdict(t) for t in plan.tasks],
                "execution_mode": plan.execution_mode,
                "original_message": message,
            }
            self.sessions.save_plan(session_key, plan_data)

            output = "[📝 Pending Plan]\n"
            output += f"Execution Mode: {plan.execution_mode}\n\n"
            for task in plan.tasks:
                output += f"- **Task**: {task.description}\n"
                output += f"  - Agent: {task.agent_name}\n"
                if task.depends_on:
                    output += f"  - Dependencies: {', '.join(task.depends_on)}\n"
            output += "\nRun `/execute` to start the plan."
            return output

        # 2. Execute plan
        result = await self.execute_plan(
            plan=plan,
            original_message=message,
            session_key=session_key,
            request_id=dispatch_id,
        )

        # 3. Save to session
        self.sessions.save_turn(session_key, message, result)

        return result

    async def execute_saved_plan(
        self,
        session_key: str,
        request_id: str | None = None,
    ) -> str:
        """
        Execute a previously saved plan.

        Args:
            session_key: Session identifier.
            request_id: Optional correlation ID for tracing.

        Returns:
            The execution result.
        """
        plan_data = self.sessions.get_plan(session_key)
        if not plan_data:
            return "Error: No pending plan found. Use `/plan <task>` to create one first."

        tasks = [SubTask(**task) for task in plan_data.get("tasks", [])]
        plan = DispatchPlan(
            tasks=tasks,
            execution_mode=plan_data.get("execution_mode", "sequential"),
        )
        original_message = plan_data.get("original_message", "execute saved plan")
        dispatch_id = request_id or uuid.uuid4().hex[:12]

        result = await self.execute_plan(
            plan=plan,
            original_message=original_message,
            session_key=session_key,
            request_id=dispatch_id,
        )

        self.sessions.save_turn(session_key, f"/execute (Original task: {original_message})", result)
        self.sessions.clear_plan(session_key)

        return result

    async def analyze_intent(self, message: str) -> DispatchPlan:
        """Analyze user intent and return a dispatch plan."""
        return await self._intent_planner.analyze_intent(message)

    async def execute_plan(
        self,
        plan: DispatchPlan,
        original_message: str,
        session_key: str,
        request_id: str,
    ) -> str:
        """Execute a dispatch plan while preserving public scheduler contract."""
        return await self._plan_executor.execute_plan(
            plan=plan,
            original_message=original_message,
            session_key=session_key,
            request_id=request_id,
        )

    def _prepare_agent_trace(self, agent: Any, task_id: str) -> None:
        """Inject trace context/config into agents that support it."""
        set_trace_context = getattr(agent, "set_trace_context", None)
        if callable(set_trace_context):
            set_trace_context(task_id=task_id)

        set_trace_capture = getattr(agent, "set_trace_capture", None)
        if callable(set_trace_capture):
            set_trace_capture(enabled=self.trace_capture, max_steps=self.max_trace_steps)

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


__all__ = ["Scheduler", "SubTask", "DispatchPlan", "TaskExecutionResult"]
