import pytest
from kubemin_agent.agents.game_audit.models import TestCase, TestPlan, AuditReportV1, TestCaseStatus

def test_testcase_creation():
    tc = TestCase(
        id="TC-01",
        description="Verify coin deduction on item purchase.",
        expected_result="-10 coins"
    )
    assert tc.id == "TC-01"
    assert tc.status == TestCaseStatus.PENDING

def test_testplan_serialization():
    tp = TestPlan(
        plan_id="PLAN-001",
        game_url="http://example.com/game",
        test_cases=[
            TestCase(id="TC-01", description="Test", expected_result="Pass")
        ]
    )
    data = tp.model_dump()
    assert data["plan_id"] == "PLAN-001"
    assert data["test_cases"][0]["status"] == "PENDING"

def test_audit_report_v1():
    report = AuditReportV1(
        status="PASS",
        game_url="http://example.com/game",
        total_vulnerabilities=0,
        critical_issues=0,
        high_issues=0,
        plan=TestPlan(plan_id="1", game_url="url"),
        markdown_report="# Good game"
    )
    assert report.status == "PASS"
    assert "url" in report.model_dump_json()
