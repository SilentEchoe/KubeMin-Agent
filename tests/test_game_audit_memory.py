import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from kubemin_agent.agent.memory.entry import MemoryEntry
from kubemin_agent.agents.game_audit.models import TestPlan
from kubemin_agent.agents.game_audit.tools import SubmitReportTool, GetPastReportsTool

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
    
    args, kwargs = agent_mock._memory.remember.call_args
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
