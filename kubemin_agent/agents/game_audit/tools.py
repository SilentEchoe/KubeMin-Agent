"""State management tools for GameAuditAgent."""

import json
from typing import Any

from kubemin_agent.agent.tools.base import Tool
from .models import TestPlan, TestCase, TestCaseStatus, AuditReportV1


class GeneratePlanTool(Tool):
    """Tool to generate and save the initial structural test plan."""

    def __init__(self, agent: Any) -> None:
        self.agent = agent

    @property
    def name(self) -> str:
        return "generate_plan"

    @property
    def description(self) -> str:
        return (
            "Use this tool to submit the initial TestPlan after reading the game guide and exploring the UI. "
            "You MUST call this tool before executing any actual test cases."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string", "description": "A unique identifier for the plan."},
                "game_url": {"type": "string", "description": "The URL of the game being tested."},
                "test_cases": {
                    "type": "array",
                    "description": "List of test cases to execute.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Unique ID for the test case, e.g. TC-001."},
                            "description": {"type": "string", "description": "What to verify."},
                            "expected_result": {"type": "string", "description": "Expected outcome according to the guide."}
                        },
                        "required": ["id", "description", "expected_result"]
                    }
                }
            },
            "required": ["plan_id", "game_url", "test_cases"]
        }

    async def execute(self, **kwargs: Any) -> str:
        cases = []
        for c in kwargs.get("test_cases", []):
            cases.append(TestCase(
                id=c["id"],
                description=c["description"],
                expected_result=c["expected_result"],
                status=TestCaseStatus.PENDING
            ))
        
        plan = TestPlan(
            plan_id=kwargs.get("plan_id"),
            game_url=kwargs.get("game_url"),
            test_cases=cases
        )
        self.agent._test_plan = plan
        return f"TestPlan '{plan.plan_id}' successfully generated with {len(cases)} test cases. Please proceed to execute them one by one."


class UpdateCaseStatusTool(Tool):
    """Tool to update the status of a specific test case."""

    def __init__(self, agent: Any) -> None:
        self.agent = agent

    @property
    def name(self) -> str:
        return "update_case_status"

    @property
    def description(self) -> str:
        return (
            "Use this tool to update the status of a test case after you have completed execution and verification."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "case_id": {"type": "string", "description": "The ID of the test case to update."},
                "status": {"type": "string", "enum": ["PASSED", "FAILED", "SKIPPED"], "description": "The new status."},
                "actual_result": {"type": "string", "description": "Observation detailing why it passed or failed."},
                "evidence_links": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of screenshot paths or log references."
                },
                "error_message": {"type": "string", "description": "Error details, if any."}
            },
            "required": ["case_id", "status", "actual_result"]
        }

    async def execute(self, **kwargs: Any) -> str:
        if not hasattr(self.agent, "_test_plan") or not self.agent._test_plan:
            return "Error: No TestPlan found. Please call generate_plan first."

        case_id = kwargs["case_id"]
        for case in self.agent._test_plan.test_cases:
            if case.id == case_id:
                case.status = TestCaseStatus(kwargs["status"])
                case.actual_result = kwargs["actual_result"]
                case.evidence_links = kwargs.get("evidence_links", [])
                case.error_message = kwargs.get("error_message")
                return f"Test case '{case_id}' status successfully updated to {case.status.value}."
                
        return f"Error: Test case '{case_id}' not found in the current TestPlan."


class SubmitReportTool(Tool):
    """Tool to finalize the audit and produce the structured JSON output."""

    def __init__(self, agent: Any) -> None:
        self.agent = agent

    @property
    def name(self) -> str:
        return "submit_report"

    @property
    def description(self) -> str:
        return (
            "Use this tool to finalize the audit run and submit the final assessment. "
            "You MUST call this when all test cases are completed."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["PASS", "FAIL", "CONDITIONAL"], "description": "Overall Assessment."},
                "total_vulnerabilities": {"type": "integer"},
                "critical_issues": {"type": "integer"},
                "high_issues": {"type": "integer"},
                "markdown_report": {"type": "string", "description": "A comprehensive markdown report string."}
            },
            "required": ["status", "total_vulnerabilities", "critical_issues", "high_issues", "markdown_report"]
        }

    async def execute(self, **kwargs: Any) -> str:
        if not hasattr(self.agent, "_test_plan") or not self.agent._test_plan:
            return "Error: No TestPlan found. Please call generate_plan first."

        report = AuditReportV1(
            status=kwargs["status"],
            game_url=self.agent._test_plan.game_url,
            total_vulnerabilities=kwargs["total_vulnerabilities"],
            critical_issues=kwargs["critical_issues"],
            high_issues=kwargs["high_issues"],
            plan=self.agent._test_plan,
            markdown_report=kwargs["markdown_report"]
        )
        
        # Save output in agent state so we can return it at the end of the run
        self.agent._final_report = report
        
        # We can also save it to workspace for persistence
        report_path = self.agent._workspace / "audit_report_v1.json"
        report_path.write_text(report.model_dump_json(indent=2))
        
        return "Report successfully submitted. The audit run is complete."
