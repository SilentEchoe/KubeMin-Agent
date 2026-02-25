"""Scheduler for intent analysis and task dispatch."""

import json
import time
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from kubemin_agent.control.audit import AuditLog
from kubemin_agent.control.registry import AgentRegistry
from kubemin_agent.control.validator import Validator
from kubemin_agent.providers.base import LLMProvider
from kubemin_agent.session.manager import SessionManager


@dataclass
class SubTask:
    """A sub-task to be dispatched to a sub-agent."""

    agent_name: str
    description: str
    depends_on: list[str] = field(default_factory=list)


@dataclass
class DispatchPlan:
    """A plan for dispatching tasks to sub-agents."""

    tasks: list[SubTask]
    execution_mode: str = "sequential"  # sequential / parallel


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
    {{"agent": "<agent_name>", "task": "<task description>"}},
    ...
  ],
  "mode": "sequential"
}}

Rules:
- Choose the most specific agent for the task
- If unsure, use "general"
- Keep task descriptions clear and actionable
- Only use multiple agents if truly necessary
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
    ) -> None:
        self.provider = provider
        self.registry = registry
        self.validator = validator
        self.audit = audit
        self.sessions = sessions

    async def dispatch(self, message: str, session_key: str) -> str:
        """
        Full dispatch flow: intent analysis -> select agent -> execute -> validate -> return.

        Args:
            message: The user's message.
            session_key: Session identifier.

        Returns:
            The final response to send back to the user.
        """
        # 1. Analyze intent
        plan = await self.analyze_intent(message)

        # 2. Execute plan
        result = await self.execute_plan(plan, message, session_key)

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
            # No agents registered, fallback
            return DispatchPlan(tasks=[SubTask(agent_name="general", description=message)])

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

    def _parse_intent(self, llm_output: str, original_message: str) -> DispatchPlan:
        """Parse LLM intent analysis output into a dispatch plan."""
        try:
            # Try to extract JSON from the response
            content = llm_output.strip()
            # Handle markdown code blocks
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            data = json.loads(content)

            # Multi-agent plan
            if "agents" in data:
                tasks = [
                    SubTask(agent_name=item["agent"], description=item["task"])
                    for item in data["agents"]
                ]
                return DispatchPlan(
                    tasks=tasks,
                    execution_mode=data.get("mode", "sequential"),
                )

            # Single agent plan
            return DispatchPlan(
                tasks=[SubTask(agent_name=data["agent"], description=data.get("task", original_message))]
            )

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning(f"Failed to parse intent: {e}, falling back to general agent")
            return DispatchPlan(tasks=[SubTask(agent_name="general", description=original_message)])

    async def execute_plan(self, plan: DispatchPlan, original_message: str, session_key: str) -> str:
        """
        Execute a dispatch plan.

        Args:
            plan: The dispatch plan.
            original_message: The original user message.
            session_key: Session identifier.

        Returns:
            Combined result from all task executions.
        """
        results: list[str] = []

        for task in plan.tasks:
            agent = self.registry.get(task.agent_name)
            if not agent:
                logger.warning(f"Agent '{task.agent_name}' not found, trying 'general'")
                agent = self.registry.get("general")
                if not agent:
                    results.append(f"Error: No agent available for task: {task.description}")
                    continue

            # Log dispatch
            self.audit.log_dispatch(session_key, original_message, agent.name, task.description)

            # Execute
            start_time = time.monotonic()
            try:
                result = await agent.run(task.description, session_key)
                duration_ms = (time.monotonic() - start_time) * 1000

                self.audit.log_execution(session_key, agent.name, result, duration_ms, success=True)
            except Exception as e:
                duration_ms = (time.monotonic() - start_time) * 1000
                result = f"Error from {agent.name}: {str(e)}"
                self.audit.log_execution(session_key, agent.name, result, duration_ms, success=False)
                logger.error(f"Agent execution failed: {agent.name} - {e}")

            # Validate
            validation = await self.validator.validate(agent.name, result)
            self.audit.log_validation(session_key, agent.name, validation.passed, validation.reason)

            if not validation.passed:
                result = f"[Validation Warning] {validation.reason}\n\n{result}"

            results.append(result)

        return "\n\n".join(results)
