"""Tests for scheduler execution semantics."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from kubemin_agent.control.audit import AuditLog
from kubemin_agent.control.registry import AgentRegistry
from kubemin_agent.control.scheduler import DispatchPlan, Scheduler, SubTask
from kubemin_agent.control.validator import Validator
from kubemin_agent.providers.base import LLMProvider, LLMResponse
from kubemin_agent.session.manager import SessionManager


class StubProvider(LLMProvider):
    """Provider stub; scheduler.execute_plan in these tests does not call analyze_intent."""

    async def chat(self, *args, **kwargs):  # type: ignore[override]
        return LLMResponse(content='{"agent":"general","task":"noop"}')

    def get_default_model(self) -> str:
        return "stub"


class _ToolNames:
    tool_names: list[str] = []


class StubAgent:
    """Minimal async agent with deterministic latency."""

    def __init__(self, name: str, delay: float = 0.0) -> None:
        self.name = name
        self.description = f"stub:{name}"
        self.tools = _ToolNames()
        self.delay = delay

    async def run(self, message: str, session_key: str, request_id: str = "") -> str:
        if self.delay > 0:
            import asyncio

            await asyncio.sleep(self.delay)
        return f"{self.name}:{message}"


def _build_scheduler(tmp_path: Path, max_parallelism: int = 4) -> tuple[Scheduler, AgentRegistry]:
    registry = AgentRegistry()
    scheduler = Scheduler(
        provider=StubProvider(),
        registry=registry,
        validator=Validator(),
        audit=AuditLog(tmp_path),
        sessions=SessionManager(tmp_path / "workspace"),
        max_parallelism=max_parallelism,
    )
    return scheduler, registry


@pytest.mark.asyncio
async def test_scheduler_respects_dependencies_in_parallel_mode(tmp_path: Path) -> None:
    scheduler, registry = _build_scheduler(tmp_path)
    registry.register(StubAgent("general"))
    registry.register(StubAgent("k8s"))

    plan = DispatchPlan(
        tasks=[
            SubTask(task_id="t1", agent_name="general", description="step-1"),
            SubTask(
                task_id="t2",
                agent_name="k8s",
                description="step-2",
                depends_on=["t1"],
            ),
        ],
        execution_mode="parallel",
    )

    output = await scheduler.execute_plan(
        plan=plan,
        original_message="root",
        session_key="cli:test",
        request_id="req-1",
    )
    parts = output.split("\n\n")

    assert parts[0].startswith("general:step-1")
    assert parts[1].startswith("k8s:step-2")


@pytest.mark.asyncio
async def test_scheduler_parallel_executes_concurrently(tmp_path: Path) -> None:
    scheduler, registry = _build_scheduler(tmp_path, max_parallelism=4)
    registry.register(StubAgent("general", delay=0.2))
    registry.register(StubAgent("k8s", delay=0.2))

    plan = DispatchPlan(
        tasks=[
            SubTask(task_id="t1", agent_name="general", description="a"),
            SubTask(task_id="t2", agent_name="k8s", description="b"),
        ],
        execution_mode="parallel",
    )

    start = time.monotonic()
    await scheduler.execute_plan(
        plan=plan,
        original_message="root",
        session_key="cli:test",
        request_id="req-2",
    )
    elapsed = time.monotonic() - start

    assert elapsed < 0.35

@pytest.mark.asyncio
async def test_scheduler_plan_mode_saves_plan(tmp_path: Path) -> None:
    scheduler, registry = _build_scheduler(tmp_path)
    registry.register(StubAgent("general"))

    # Act: Dispatch with plan_mode=True
    response = await scheduler.dispatch(
        message="do something",
        session_key="cli:test_plan",
        plan_mode=True,
    )

    assert "[📝 Pending Plan]" in response
    assert "Run `/execute` to start the plan." in response

    # Assert: Plan is saved in session
    plan_data = scheduler.sessions.get_plan("cli:test_plan")
    assert plan_data is not None
    assert plan_data["original_message"] == "do something"
    assert len(plan_data["tasks"]) == 1
    assert plan_data["tasks"][0]["agent_name"] == "general"

@pytest.mark.asyncio
async def test_scheduler_execute_saved_plan(tmp_path: Path) -> None:
    scheduler, registry = _build_scheduler(tmp_path)
    registry.register(StubAgent("general"))

    # Act 1: Create a plan
    await scheduler.dispatch(
        message="do something",
        session_key="cli:test_plan_execute",
        plan_mode=True,
    )
    
    assert scheduler.sessions.get_plan("cli:test_plan_execute") is not None

    # Act 2: Execute the saved plan
    response = await scheduler.execute_saved_plan(
        session_key="cli:test_plan_execute",
    )

    # Assert: Execution happened and plan is cleared
    assert "general:noop" in response
    assert scheduler.sessions.get_plan("cli:test_plan_execute") is None
