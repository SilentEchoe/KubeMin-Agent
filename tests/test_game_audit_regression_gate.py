import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from kubemin_agent.agent.memory.entry import MemoryEntry
from kubemin_agent.agents.game_audit.models import FSMNode, TestCase, TestCaseStatus, TestPlan
from kubemin_agent.agents.game_audit.tools import EvaluateRegressionGateTool


def _parse_result_payload(result: str) -> dict:
    return json.loads(result.split("\n", 1)[1])


@pytest.mark.asyncio
async def test_regression_gate_pass_when_no_issues():
    agent = SimpleNamespace(
        _memory=AsyncMock(),
        _test_plan=TestPlan(plan_id="p1", game_url="http://test.com/game"),
    )
    agent._memory.recall.return_value = []

    tool = EvaluateRegressionGateTool(agent)
    payload = _parse_result_payload(await tool.execute(game_url="http://test.com/game"))

    assert payload["recommendation"] == "PASS"
    assert payload["gate_score"] == 100
    assert payload["persistent_failures"] == []


@pytest.mark.asyncio
async def test_regression_gate_fail_on_unresolved_persistent_failures():
    report_1 = {
        "plan": {"test_cases": [{"id": "TC-1", "status": "FAILED"}], "nodes": []},
    }
    report_2 = {
        "plan": {"test_cases": [{"id": "TC-1", "status": "FAILED"}], "nodes": []},
    }
    agent = SimpleNamespace(_memory=AsyncMock(), _test_plan=None)
    agent._memory.recall.return_value = [
        MemoryEntry(id="m1", content=json.dumps(report_1), tags=["game_audit"], source="agent"),
        MemoryEntry(id="m2", content=json.dumps(report_2), tags=["game_audit"], source="agent"),
    ]

    tool = EvaluateRegressionGateTool(agent)
    payload = _parse_result_payload(
        await tool.execute(game_url="http://test.com/game", current_failed_cases=["TC-1"])
    )

    assert payload["recommendation"] == "FAIL"
    assert payload["persistent_failures"] == ["TC-1"]
    assert payload["unresolved_persistent_failures"] == ["TC-1"]


@pytest.mark.asyncio
async def test_regression_gate_uses_current_plan_when_failed_cases_not_provided():
    report = {
        "plan": {"test_cases": [], "nodes": [{"assertions": [{"id": "AC-1", "status": "FAILED"}]}]},
    }
    plan = TestPlan(
        plan_id="p2",
        game_url="http://test.com/game",
        nodes=[
            FSMNode(
                id="node-1",
                description="node",
                assertions=[
                    TestCase(
                        id="AC-1",
                        description="assertion",
                        expected_result="ok",
                        status=TestCaseStatus.FAILED,
                    )
                ],
            )
        ],
    )
    agent = SimpleNamespace(_memory=AsyncMock(), _test_plan=plan)
    agent._memory.recall.return_value = [
        MemoryEntry(id="m1", content=json.dumps(report), tags=["game_audit"], source="agent"),
    ]

    tool = EvaluateRegressionGateTool(agent)
    payload = _parse_result_payload(await tool.execute(game_url="http://test.com/game"))

    assert payload["current_failed_cases"] == ["AC-1"]
    assert payload["recommendation"] == "FAIL"
