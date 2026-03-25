"""Shared types for scheduler planning and execution."""

from __future__ import annotations

from dataclasses import dataclass, field


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
