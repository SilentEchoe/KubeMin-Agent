"""Scheduler for intent analysis and task dispatch."""

from __future__ import annotations

import asyncio
import dataclasses
import inspect
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from kubemin_agent.control.agent_context import AgentContextStore, ContextEnvelope
from kubemin_agent.control.audit import AuditLog
from kubemin_agent.control.evaluation import ExecutionEvaluator
from kubemin_agent.control.registry import AgentRegistry
from kubemin_agent.control.validator import Validator
from kubemin_agent.providers.base import LLMProvider
from kubemin_agent.session.manager import SessionManager


@dataclass
class SubTask:
    """A sub-task to be dispatched to a sub-agent."""

    task_id: str
    agent_name: str
    description: str
    depends_on: list[str] = field(default_factory=list)


@dataclass
class DispatchPlan:
    """A plan for dispatching tasks to sub-agents."""

    tasks: list[SubTask]
    execution_mode: str = "sequential"  # sequential / parallel


@dataclass
class TaskExecutionResult:
    """Execution result for a single task."""

    task_id: str
    content: str
    agent_name: str = ""
    failed: bool = False


INTENT_SYSTEM_PROMPT = """You are a task router for KubeMin-Agent, an Agent Control Plane.

Your job is to analyze the user's message and decide which sub-agent should handle it.

Available sub-agents:
{agents_description}

Respond with a JSON object:
{{
  "agent": "<agent_name>",
  "task": "<reformulated task description for the chosen agent>"
}}

If the task requires multiple agents, respond with:
{{
  "agents": [
    {{
      "task_id": "t1",
      "agent": "<agent_name>",
      "task": "<task description>",
      "depends_on": []
    }}
  ],
  "mode": "sequential"
}}

Rules:
- Choose the most specific agent for the task
- If unsure, use "general"
- Keep task descriptions clear and actionable
- Only use multiple agents if truly necessary
- mode can be "sequential" or "parallel"
- depends_on should reference task_id values
"""


class Scheduler:
    """
    Core scheduler for the control plane.

    Analyzes user intent via LLM, selects the appropriate sub-agent,
    dispatches tasks, validates results, and records audit logs.
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

    async def dispatch(
        self,
        message: str,
        session_key: str,
        request_id: str | None = None,
        plan_mode: bool = False,
    ) -> str:
        """
        Full dispatch flow: intent analysis -> select agent -> execute -> validate -> return.

        Args:
            message: The user's message.
            session_key: Session identifier.
            request_id: Optional correlation ID for tracing.
            plan_mode: If True, generate and save the plan without executing it.

        Returns:
            The final response to send back to the user or the formatted plan.
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
            for t in plan.tasks:
                output += f"- **Task**: {t.description}\n"
                output += f"  - Agent: {t.agent_name}\n"
                if t.depends_on:
                    output += f"  - Dependencies: {', '.join(t.depends_on)}\n"
            output += "\nRun `/execute` to start the plan."
            return output

        # 2. Execute plan
        result = await self.execute_plan(plan, message, session_key, request_id=dispatch_id)

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

        tasks = [
            SubTask(**t) for t in plan_data.get("tasks", [])
        ]
        plan = DispatchPlan(tasks=tasks, execution_mode=plan_data.get("execution_mode", "sequential"))
        original_message = plan_data.get("original_message", "execute saved plan")
        dispatch_id = request_id or uuid.uuid4().hex[:12]

        result = await self.execute_plan(plan, original_message, session_key, request_id=dispatch_id)

        self.sessions.save_turn(session_key, f"/execute (Original task: {original_message})", result)
        self.sessions.clear_plan(session_key)

        return result

    async def analyze_intent(self, message: str) -> DispatchPlan:
        """
        Analyze user intent using LLM to determine which agent(s) to dispatch to.

        Args:
            message: The user's message.

        Returns:
            A dispatch plan with target agents.
        """
        agents_desc = self.registry.get_routing_context()
        if not agents_desc:
            return DispatchPlan(
                tasks=[SubTask(task_id="t1", agent_name="general", description=message)]
            )

        system_prompt = INTENT_SYSTEM_PROMPT.format(agents_description=agents_desc)

        response = await self.provider.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            max_tokens=512,
            temperature=0.0,
        )

        return self._parse_intent(response.content or "", message)

    def _extract_json_content(self, llm_output: str) -> str:
        """Extract JSON payload from model output."""
        content = llm_output.strip()
        if not content.startswith("```"):
            return content

        lines = content.splitlines()
        if len(lines) < 3:
            return content

        body = lines[1:-1]
        if body and body[0].strip().lower() == "json":
            body = body[1:]
        return "\n".join(body).strip()

    def _normalize_plan(self, tasks: list[SubTask], mode: str) -> DispatchPlan:
        """Normalize execution mode and dependency references."""
        valid_mode = mode if mode in {"sequential", "parallel"} else "sequential"
        known = {task.task_id for task in tasks}
        for task in tasks:
            task.depends_on = [dep for dep in task.depends_on if dep in known and dep != task.task_id]
        return DispatchPlan(tasks=tasks, execution_mode=valid_mode)

    def _parse_intent(self, llm_output: str, original_message: str) -> DispatchPlan:
        """Parse LLM intent analysis output into a dispatch plan."""
        try:
            content = self._extract_json_content(llm_output)
            data = json.loads(content)

            if "agents" in data:
                tasks: list[SubTask] = []
                for idx, item in enumerate(data["agents"]):
                    task_id = str(item.get("task_id") or f"t{idx + 1}")
                    depends_on = item.get("depends_on") or []
                    if not isinstance(depends_on, list):
                        depends_on = []
                    tasks.append(
                        SubTask(
                            task_id=task_id,
                            agent_name=item["agent"],
                            description=item["task"],
                            depends_on=[str(dep) for dep in depends_on],
                        )
                    )
                return self._normalize_plan(tasks, str(data.get("mode", "sequential")))

            return self._normalize_plan(
                tasks=[
                    SubTask(
                        task_id="t1",
                        agent_name=data["agent"],
                        description=data.get("task", original_message),
                    )
                ],
                mode="sequential",
            )
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
            logger.warning(f"Failed to parse intent: {e}, falling back to general agent")
            return DispatchPlan(
                tasks=[SubTask(task_id="t1", agent_name="general", description=original_message)]
            )

    async def execute_plan(
        self,
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
            
        # Initialize the active plan document
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
            
            # Mark task in progress
            self.sessions.update_active_plan_task_status(session_key, task.task_id, "[-]")
            
            # Read active plan content
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
            
            # Get summary and update task as completed
            summary_text = context_store._summarize_result(task_result.content)
            self.sessions.update_active_plan_task_status(session_key, task.task_id, "[x]", summary_text)
            
            context_store.add_result(
                task_id=task.task_id,
                agent_name=task_result.agent_name or task.agent_name,
                result=task_result.content,
            )

            if self.fail_fast and task_result.failed:
                stopped_by_fail_fast = True
                break

        # Generate final execution report via LLM
        raw_results_prompt = f"Original Objective: {original_message}\n\nTask Results:\n"
        
        for task_id in execution_order:
            if task_id in results:
                res = results[task_id]
                status = "FAILED" if res.failed else "SUCCESS"
                raw_results_prompt += f"--- Task {task_id} ({res.agent_name}) [{status}] ---\n{res.content}\n\n"
                
        if stopped_by_fail_fast and remaining:
            skipped = ", ".join(sorted(remaining.keys()))
            raw_results_prompt += f"--- Skipped Tasks ---\n{skipped} (due to fail_fast)\n\n"

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
                    {"role": "user", "content": raw_results_prompt}
                ]
            )
            final_report = report_response.content or "Error generating report."
        except Exception as e:
            logger.error(f"Failed to generate final report via LLM: {e}")
            final_report = "Error: Plan completed but final report generation failed.\n\nRaw Results Preview:\n" + raw_results_prompt[:1000]

        return final_report

    async def _execute_parallel_round(
        self,
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
            
            # Read active plan content (once for the round)
            plan_path = self.sessions.get_active_plan_doc_path(session_key)
            active_plan_text = plan_path.read_text(encoding="utf-8") if plan_path else "" 

            # Mark tasks in progress
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
                
                # Get summary and update task as completed
                summary_text = context_store._summarize_result(task_result.content)
                self.sessions.update_active_plan_task_status(session_key, task.task_id, "[x]", summary_text)
                
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
        """Run an agent while keeping backward compatibility for legacy run signatures."""
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
