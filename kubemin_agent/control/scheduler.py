"""Scheduler for intent analysis and task dispatch."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field

from loguru import logger

from kubemin_agent.control.audit import AuditLog
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
        max_parallelism: int = 4,
        fail_fast: bool = False,
    ) -> None:
        self.provider = provider
        self.registry = registry
        self.validator = validator
        self.audit = audit
        self.sessions = sessions
        self.max_parallelism = max(1, max_parallelism)
        self.fail_fast = fail_fast

    async def dispatch(
        self,
        message: str,
        session_key: str,
        request_id: str | None = None,
    ) -> str:
        """
        Full dispatch flow: intent analysis -> select agent -> execute -> validate -> return.

        Args:
            message: The user's message.
            session_key: Session identifier.
            request_id: Optional correlation ID for tracing.

        Returns:
            The final response to send back to the user.
        """
        dispatch_id = request_id or uuid.uuid4().hex[:12]

        # 1. Analyze intent
        plan = await self.analyze_intent(message)

        # 2. Execute plan
        result = await self.execute_plan(plan, message, session_key, request_id=dispatch_id)

        # 3. Save to session
        self.sessions.save_turn(session_key, message, result)

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

        index_map = {task.task_id: idx for idx, task in enumerate(plan.tasks)}
        remaining = {task.task_id: task for task in plan.tasks}
        completed: set[str] = set()
        results: dict[str, TaskExecutionResult] = {}
        execution_order: list[str] = []
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
                    original_message=original_message,
                    session_key=session_key,
                    request_id=request_id,
                )
                if self.fail_fast and failed_in_round:
                    stopped_by_fail_fast = True
                    break
                continue

            task = ready[0]
            task_result = await self._execute_task(
                task=task,
                original_message=original_message,
                session_key=session_key,
                request_id=request_id,
            )
            results[task.task_id] = task_result
            execution_order.append(task.task_id)
            remaining.pop(task.task_id, None)
            completed.add(task.task_id)

            if self.fail_fast and task_result.failed:
                stopped_by_fail_fast = True
                break

        output_parts = [results[task_id].content for task_id in execution_order if task_id in results]
        if stopped_by_fail_fast and remaining:
            skipped = ", ".join(sorted(remaining.keys()))
            output_parts.append(f"[Scheduler] fail_fast enabled, skipped tasks: {skipped}")

        return "\n\n".join(output_parts)

    async def _execute_parallel_round(
        self,
        ready: list[SubTask],
        remaining: dict[str, SubTask],
        completed: set[str],
        results: dict[str, TaskExecutionResult],
        execution_order: list[str],
        original_message: str,
        session_key: str,
        request_id: str,
    ) -> bool:
        """Execute one dependency-resolved round in parallel."""
        failed_in_round = False

        for i in range(0, len(ready), self.max_parallelism):
            chunk = ready[i : i + self.max_parallelism]
            chunk_results = await asyncio.gather(
                *[
                    self._execute_task(
                        task=task,
                        original_message=original_message,
                        session_key=session_key,
                        request_id=request_id,
                    )
                    for task in chunk
                ]
            )

            for task, task_result in zip(chunk, chunk_results, strict=True):
                results[task.task_id] = task_result
                execution_order.append(task.task_id)
                remaining.pop(task.task_id, None)
                completed.add(task.task_id)
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
                    failed=True,
                )

        self.audit.log_dispatch(
            session_key=session_key,
            message=original_message,
            agent_name=agent.name,
            task_description=task.description,
            request_id=request_id,
        )

        start_time = time.monotonic()
        failed = False

        try:
            result = await agent.run(task.description, session_key, request_id=request_id)
            duration_ms = (time.monotonic() - start_time) * 1000
            self.audit.log_execution(
                session_key=session_key,
                agent_name=agent.name,
                result_preview=result,
                duration_ms=duration_ms,
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
                success=False,
                request_id=request_id,
            )
            logger.error(f"Agent execution failed: {agent.name} - {e}")

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
            reason=validation.reason,
            request_id=request_id,
            severity=validation.severity,
            policy_id=validation.policy_id,
            redactions=validation.redactions,
        )

        if not validation.passed:
            if validation.severity == "block":
                return TaskExecutionResult(
                    task_id=task.task_id,
                    content=f"[Validation Blocked] {validation.reason}\n\n{sanitized}",
                    failed=True,
                )

            sanitized = f"[Validation Warning] {validation.reason}\n\n{sanitized}"

        return TaskExecutionResult(task_id=task.task_id, content=sanitized, failed=failed)
