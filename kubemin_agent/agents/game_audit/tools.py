"""State management tools for GameAuditAgent."""

import json
from typing import Any

from kubemin_agent.agent.tools.base import Tool
from .models import TestPlan, TestCase, TestCaseStatus, AuditReportV1, FSMNode, FSMEdge
from .exceptions import SuspendExecutionException


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
                    "description": "List of global independent test cases.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "description": {"type": "string"},
                            "expected_result": {"type": "string"}
                        },
                        "required": ["id", "description", "expected_result"]
                    }
                },
                "nodes": {
                    "type": "array",
                    "description": "List of FSM nodes (pages/states).",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "e.g., 'HomeContext'"},
                            "description": {"type": "string"},
                            "assertions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "description": {"type": "string"},
                                        "expected_result": {"type": "string"}
                                    },
                                    "required": ["id", "description", "expected_result"]
                                }
                            }
                        },
                        "required": ["id", "description"]
                    }
                },
                "edges": {
                    "type": "array",
                    "description": "List of FSM edges (transitions).",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "e.g., 'E-001'"},
                            "source_node_id": {"type": "string"},
                            "target_node_id": {"type": "string"},
                            "action_description": {"type": "string"}
                        },
                        "required": ["id", "source_node_id", "target_node_id", "action_description"]
                    }
                }
            },
            "required": ["plan_id", "game_url", "nodes", "edges"]
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
            
        nodes = []
        for n in kwargs.get("nodes", []):
            node_assertions = []
            for ac in n.get("assertions", []):
                node_assertions.append(TestCase(
                    id=ac["id"],
                    description=ac["description"],
                    expected_result=ac["expected_result"],
                    status=TestCaseStatus.PENDING
                ))
            nodes.append(FSMNode(
                id=n["id"],
                description=n["description"],
                assertions=node_assertions
            ))
            
        edges = []
        for e in kwargs.get("edges", []):
            edges.append(FSMEdge(
                id=e["id"],
                source_node_id=e["source_node_id"],
                target_node_id=e["target_node_id"],
                action_description=e["action_description"]
            ))
        
        plan = TestPlan(
            plan_id=kwargs.get("plan_id"),
            game_url=kwargs.get("game_url"),
            test_cases=cases,
            nodes=nodes,
            edges=edges
        )
        self.agent._test_plan = plan
        return f"TestPlan '{plan.plan_id}' generated successfully with {len(nodes)} FSM nodes and {len(edges)} edges. Please proceed to explore the graph."


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
        
        # Search global cases
        for case in self.agent._test_plan.test_cases:
            if case.id == case_id:
                case.status = TestCaseStatus(kwargs["status"])
                case.actual_result = kwargs["actual_result"]
                case.evidence_links = kwargs.get("evidence_links", [])
                case.error_message = kwargs.get("error_message")
                return f"Global test case '{case_id}' status successfully updated to {case.status.value}."
                
        # Search node assertions
        for node in self.agent._test_plan.nodes:
            for case in node.assertions:
                if case.id == case_id:
                    # Update node status logic: mark node visited if we are executing its cases
                    node.is_visited = True
                    case.status = TestCaseStatus(kwargs["status"])
                    case.actual_result = kwargs["actual_result"]
                    case.evidence_links = kwargs.get("evidence_links", [])
                    case.error_message = kwargs.get("error_message")
                    return f"Assertion '{case_id}' on node '{node.id}' successfully updated to {case.status.value}."
                
        return f"Error: Test case/Assertion '{case_id}' not found in the current TestPlan (neither global nor within nodes)."


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
                "fsm_node_coverage": {"type": "number", "description": "Percentage of nodes visited (0.0 to 1.0)."},
                "fsm_edge_coverage": {"type": "number", "description": "Percentage of edges successfully traversed (0.0 to 1.0)."},
                "markdown_report": {"type": "string", "description": "A comprehensive markdown report string."}
            },
            "required": ["status", "total_vulnerabilities", "critical_issues", "high_issues", "fsm_node_coverage", "markdown_report"]
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
            fsm_node_coverage=kwargs.get("fsm_node_coverage", 0.0),
            fsm_edge_coverage=kwargs.get("fsm_edge_coverage", 0.0),
            plan=self.agent._test_plan,
            markdown_report=kwargs["markdown_report"]
        )
        
        # Save output in agent state so we can return it at the end of the run
        self.agent._final_report = report
        
        # We can also save it to workspace for persistence
        report_path = self.agent._workspace / "audit_report_v1.json"
        
        # Save to MemoryStore for cross-run history
        if hasattr(self.agent, "_memory") and self.agent._memory:
            await self.agent._memory.remember(
                content=report.model_dump_json(indent=2),
                tags=["game_audit", self.agent._test_plan.game_url]
            )

        report_path.write_text(report.model_dump_json(indent=2))
        return "Report successfully submitted and saved to memory. The audit run is complete."


class RequestHumanReviewTool(Tool):
    """Tool to request human intervention and suspend the agent run."""

    def __init__(self, agent: Any) -> None:
        self.agent = agent

    @property
    def name(self) -> str:
        return "request_human_review"

    @property
    def description(self) -> str:
        return (
            "Use this tool when you encounter an ambiguous situation, low-confidence finding, "
            "or a CAPTCHA that you cannot bypass. This will suspend your execution and ask "
            "a human operator for help or clarification."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why human help is needed (e.g. 'Is this image compliant with the policy?')."},
                "case_id": {"type": "string", "description": "The ID of the test case currently being executed."},
                "screenshot_path": {"type": "string", "description": "Optional path to a screenshot showing the issue."}
            },
            "required": ["reason", "case_id"]
        }

    async def execute(self, **kwargs: Any) -> str:
        case_id = kwargs["case_id"]
        
        # Optionally, mark the case as PENDING_REVIEW if we have a test plan
        if hasattr(self.agent, "_test_plan") and self.agent._test_plan:
            for case in self.agent._test_plan.test_cases:
                if case.id == case_id:
                    case.status = TestCaseStatus.PENDING_REVIEW
                    break

        raise SuspendExecutionException(
            reason=kwargs["reason"],
            case_id=case_id,
            screenshot_path=kwargs.get("screenshot_path", "")
        )

class GetPastReportsTool(Tool):
    """Tool to retrieve historical audit reports for a specific game."""

    def __init__(self, agent: Any) -> None:
        self.agent = agent

    @property
    def name(self) -> str:
        return "get_past_reports"

    @property
    def description(self) -> str:
        return (
            "Use this tool before creating a TestPlan to check if this game has been audited before. "
            "It returns previous AuditReportV1 JSONs from the memory store. You can use this "
            "to check if past bugs (FAILED test cases) have been fixed."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "game_url": {"type": "string", "description": "The URL of the game."},
                "limit": {"type": "integer", "description": "Maximum number of past reports to return. Default is 5."}
            },
            "required": ["game_url"]
        }

    async def execute(self, **kwargs: Any) -> str:
        if not hasattr(self.agent, "_memory") or not self.agent._memory:
            return "Error: Memory store is not available."

        game_url = kwargs["game_url"]
        limit = kwargs.get("limit", 5)
        
        # Search for exact game_url in tags or query
        query = f"game_audit {game_url}"
        memories = await self.agent._memory.recall(query=query, top_k=limit)
        
        if not memories:
            return f"No past reports found for {game_url}."
            
        reports = []
        for i, m in enumerate(memories):
            try:
                # We expect the content to be the JSON string of AuditReportV1
                reports.append(f"--- Past Report {i+1} ({m.created_at}) ---\n{m.content}")
            except Exception:
                pass
                
        if not reports:
            return f"No valid past reports found for {game_url}."
            
        return "\n\n".join(reports)

