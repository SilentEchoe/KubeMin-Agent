"""Intent planning logic extracted from Scheduler."""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from kubemin_agent.control.registry import AgentRegistry
from kubemin_agent.control.scheduler_types import DispatchPlan, SubTask
from kubemin_agent.providers.base import LLMProvider

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


class IntentPlanner:
    """LLM-backed planner that analyzes user intent and builds dispatch plans."""

    def __init__(self, provider: LLMProvider, registry: AgentRegistry) -> None:
        self.provider = provider
        self.registry = registry

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
        )

        return self.parse_intent(response.content or "", message)

    def extract_json_content(self, llm_output: str) -> str:
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

    def normalize_plan(self, tasks: list[SubTask], mode: str) -> DispatchPlan:
        """Normalize execution mode and dependency references."""
        valid_mode = mode if mode in {"sequential", "parallel"} else "sequential"
        known = {task.task_id for task in tasks}
        for task in tasks:
            task.depends_on = [dep for dep in task.depends_on if dep in known and dep != task.task_id]
        return DispatchPlan(tasks=tasks, execution_mode=valid_mode)

    def parse_intent(self, llm_output: str, original_message: str) -> DispatchPlan:
        """Parse LLM intent analysis output into a dispatch plan."""
        try:
            content = self.extract_json_content(llm_output)
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
                return self.normalize_plan(tasks, str(data.get("mode", "sequential")))

            return self.normalize_plan(
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

    @staticmethod
    def plan_to_dict(plan: DispatchPlan, original_message: str) -> dict[str, Any]:
        """Serialize a dispatch plan for persistence."""
        return {
            "tasks": [
                {
                    "task_id": task.task_id,
                    "agent_name": task.agent_name,
                    "description": task.description,
                    "depends_on": task.depends_on,
                }
                for task in plan.tasks
            ],
            "execution_mode": plan.execution_mode,
            "original_message": original_message,
        }
