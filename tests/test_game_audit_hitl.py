import pytest
from types import SimpleNamespace
from kubemin_agent.agents.game_audit.models import TestPlan, TestCase
from kubemin_agent.agents.game_audit.tools import RequestHumanReviewTool
from kubemin_agent.agents.game_audit.exceptions import SuspendExecutionException

@pytest.mark.asyncio
async def test_request_human_review_tool_raises_exception():
    agent_mock = SimpleNamespace(_test_plan=TestPlan(
        plan_id="plan-1", game_url="test", test_cases=[
            TestCase(id="TC-1", description="Test captcha", expected_result="passed")
        ]
    ))
    
    tool = RequestHumanReviewTool(agent_mock)
    
    with pytest.raises(SuspendExecutionException) as exc_info:
        await tool.execute(case_id="TC-1", reason="Need help with Captcha", screenshot_path="/tmp/captcha.png")
        
    assert exc_info.value.reason == "Need help with Captcha"
    assert exc_info.value.case_id == "TC-1"
    
    # Verify the test case status was updated
    assert agent_mock._test_plan.test_cases[0].status == "PENDING_REVIEW"
