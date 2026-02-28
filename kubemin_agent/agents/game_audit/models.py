"""Pydantic models for GameAuditAgent state machine and reporting."""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class TestCaseStatus(str, Enum):
    """Execution status of a single test case."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    PENDING_REVIEW = "PENDING_REVIEW"


class TestCase(BaseModel):
    """A specific test case derived from the PDF guide and game rules."""
    id: str = Field(..., description="Unique identifier for the test case (e.g., 'TC-001').")
    description: str = Field(..., description="What this test case is verifying.")
    expected_result: str = Field(..., description="The expected outcome according to the guide.")
    status: TestCaseStatus = Field(default=TestCaseStatus.PENDING, description="Current status of the test case.")
    actual_result: Optional[str] = Field(None, description="The actual outcome observed during testing.")
    evidence_links: List[str] = Field(default_factory=list, description="List of screenshot paths or log references supporting the finding.")
    error_message: Optional[str] = Field(None, description="Error message if the test case failed or threw an exception.")


class TestPlan(BaseModel):
    """The overall test plan generated after initial exploration."""
    plan_id: str = Field(..., description="Unique identifier for this test plan.")
    game_url: str = Field(..., description="The URL of the game being tested.")
    status: str = Field(default="IN_PROGRESS", description="Status of the overall plan (e.g., IN_PROGRESS, COMPLETED, ABORTED).")
    test_cases: List[TestCase] = Field(default_factory=list, description="List of test cases to execute.")


class AuditReportV1(BaseModel):
    """Structured CI-friendly JSON output for the final audit report."""
    status: str = Field(..., description="Overall assessment: PASS, FAIL, or CONDITIONAL.")
    game_url: str = Field(..., description="The URL of the game tested.")
    total_vulnerabilities: int = Field(default=0, description="Total number of issues found.")
    critical_issues: int = Field(default=0, description="Number of critical issues (e.g., prompt injection, security flaws).")
    high_issues: int = Field(default=0, description="Number of high severity issues (e.g., broken logic, policy violations).")
    plan: TestPlan = Field(..., description="The finalized test plan with execution results.")
    markdown_report: str = Field(..., description="A human-readable markdown summary of the audit.")
