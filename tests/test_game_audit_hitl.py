from types import SimpleNamespace

import pytest

from kubemin_agent.agents.game_audit.exceptions import SuspendExecutionException
from kubemin_agent.agents.game_audit.models import FSMNode, TestCase, TestPlan
from kubemin_agent.agents.game_audit.tools import RequestHumanReviewTool


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


@pytest.mark.asyncio
async def test_request_human_review_updates_node_assertion_status():
    agent_mock = SimpleNamespace(
        _test_plan=TestPlan(
            plan_id="plan-2",
            game_url="test",
            nodes=[
                FSMNode(
                    id="node-1",
                    description="node",
                    assertions=[
                        TestCase(id="AC-1", description="assertion", expected_result="passed")
                    ],
                )
            ],
        )
    )

    tool = RequestHumanReviewTool(agent_mock)

    with pytest.raises(SuspendExecutionException):
        await tool.execute(case_id="AC-1", reason="Need manual verify")

    assert agent_mock._test_plan.nodes[0].is_visited is True
    assert agent_mock._test_plan.nodes[0].assertions[0].status == "PENDING_REVIEW"
