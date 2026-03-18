import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from kubemin_agent.agent.memory.entry import MemoryEntry
from kubemin_agent.agents.game_audit.models import TestPlan
from kubemin_agent.agents.game_audit.tools import GetPastReportsTool, SubmitReportTool


@pytest.mark.asyncio
async def test_submit_report_saves_to_memory(tmp_path):
    agent_mock = SimpleNamespace(
        _test_plan=TestPlan(plan_id="p1", game_url="http://test.com/game"),
        _memory=AsyncMock(),
        _workspace=tmp_path
    )

    tool = SubmitReportTool(agent_mock)
    res = await tool.execute(
        status="PASS",
        total_vulnerabilities=0,
        critical_issues=0,
        high_issues=0,
        markdown_report="All good"
    )

    assert "saved to memory" in res
    agent_mock._memory.remember.assert_called_once()

    _, kwargs = agent_mock._memory.remember.call_args
    assert "http://test.com/game" in kwargs["tags"]
    assert "game_audit" in kwargs["tags"]
    assert "All good" in kwargs["content"]

@pytest.mark.asyncio
async def test_get_past_reports():
    agent_mock = SimpleNamespace(
        _memory=AsyncMock()
    )

    mock_entry = MemoryEntry(
        id="mem-1",
        content='{"status": "FAIL", "markdown_report": "Bug found"}',
        tags=["game_audit", "http://test.com/game"],
        source="agent"
    )

    agent_mock._memory.recall.return_value = [mock_entry]

    tool = GetPastReportsTool(agent_mock)
    res = await tool.execute(game_url="http://test.com/game")

    agent_mock._memory.recall.assert_called_once_with(
        query="game_audit http://test.com/game",
        top_k=5
    )
    assert "Bug found" in res
    assert "Past Report 1" in res
    assert "Historical summary" in res


@pytest.mark.asyncio
async def test_get_past_reports_finds_persistent_failures():
    agent_mock = SimpleNamespace(_memory=AsyncMock())

    report_1 = {
        "status": "FAIL",
        "markdown_report": "Run-1",
        "plan": {
            "test_cases": [
                {"id": "TC-1", "status": "FAILED"},
                {"id": "TC-2", "status": "PASSED"},
            ],
            "nodes": [],
        },
    }
    report_2 = {
        "status": "CONDITIONAL",
        "markdown_report": "Run-2",
        "plan": {
            "test_cases": [
                {"id": "TC-1", "status": "FAILED"},
                {"id": "TC-3", "status": "FAILED"},
            ],
            "nodes": [],
        },
    }

    agent_mock._memory.recall.return_value = [
        MemoryEntry(id="m1", content=json.dumps(report_1), tags=["game_audit"], source="agent"),
        MemoryEntry(id="m2", content=json.dumps(report_2), tags=["game_audit"], source="agent"),
    ]

    tool = GetPastReportsTool(agent_mock)
    res = await tool.execute(game_url="http://test.com/game", limit=2)

    assert "persistent_failures=TC-1" in res
    assert "failed_cases=TC-1" in res


@pytest.mark.asyncio
async def test_get_past_reports_full_mode_keeps_raw_payload():
    agent_mock = SimpleNamespace(_memory=AsyncMock())
    raw = '{"status":"FAIL","markdown_report":"raw"}'
    agent_mock._memory.recall.return_value = [
        MemoryEntry(id="m1", content=raw, tags=["game_audit"], source="agent")
    ]

    tool = GetPastReportsTool(agent_mock)
    res = await tool.execute(game_url="http://test.com/game", mode="full")
    assert raw in res


@pytest.mark.asyncio
async def test_submit_report_fallback_for_missing_fields(tmp_path):
    agent_mock = SimpleNamespace(
        _test_plan=TestPlan(plan_id="p2", game_url="http://test.com/game"),
        _memory=AsyncMock(),
        _workspace=tmp_path,
    )

    tool = SubmitReportTool(agent_mock)
    res = await tool.execute(status="CONDITIONAL")

    assert "saved to memory" in res
    assert "Validation warnings" in res
    assert agent_mock._final_report.total_vulnerabilities == 0
    assert agent_mock._final_report.fsm_node_coverage == 0.0
    assert "# Game Audit Report" in agent_mock._final_report.markdown_report


@pytest.mark.asyncio
async def test_submit_report_rejects_invalid_coverage(tmp_path):
    agent_mock = SimpleNamespace(
        _test_plan=TestPlan(plan_id="p3", game_url="http://test.com/game"),
        _memory=AsyncMock(),
        _workspace=tmp_path,
    )

    tool = SubmitReportTool(agent_mock)
    res = await tool.execute(status="PASS", fsm_node_coverage=1.2)
    assert "fsm_node_coverage must be between 0.0 and 1.0" in res


@pytest.mark.asyncio
async def test_submit_report_normalizes_inconsistent_totals(tmp_path):
    agent_mock = SimpleNamespace(
        _test_plan=TestPlan(plan_id="p4", game_url="http://test.com/game"),
        _memory=AsyncMock(),
        _workspace=tmp_path,
    )

    tool = SubmitReportTool(agent_mock)
    res = await tool.execute(
        status="PASS",
        total_vulnerabilities=1,
        critical_issues=1,
        high_issues=2,
        markdown_report="report",
    )

    assert "Validation warnings" in res
    assert agent_mock._final_report.total_vulnerabilities == 3
    assert agent_mock._final_report.status == "CONDITIONAL"
