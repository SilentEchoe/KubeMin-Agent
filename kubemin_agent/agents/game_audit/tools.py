"""State management tools for GameAuditAgent."""

import json
from typing import Any

from kubemin_agent.agent.tools.base import Tool

from .exceptions import SuspendExecutionException
from .models import AuditReportV1, FSMEdge, FSMNode, TestCase, TestCaseStatus, TestPlan


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
            "required": ["status"]
        }

    async def execute(self, **kwargs: Any) -> str:
        if not hasattr(self.agent, "_test_plan") or not self.agent._test_plan:
            return "Error: No TestPlan found. Please call generate_plan first."

        status = self._normalize_status(kwargs.get("status", "CONDITIONAL"))
        if status is None:
            return "Error: status must be one of PASS/FAIL/CONDITIONAL."

        critical_issues, err = self._to_non_negative_int(kwargs.get("critical_issues", 0), "critical_issues")
        if err:
            return err
        high_issues, err = self._to_non_negative_int(kwargs.get("high_issues", 0), "high_issues")
        if err:
            return err

        warnings: list[str] = []

        total_raw = kwargs.get("total_vulnerabilities")
        if total_raw is None:
            total_vulnerabilities = critical_issues + high_issues
            warnings.append("total_vulnerabilities missing, fallback to critical_issues + high_issues.")
        else:
            total_vulnerabilities, err = self._to_non_negative_int(total_raw, "total_vulnerabilities")
            if err:
                return err
            minimum_total = critical_issues + high_issues
            if total_vulnerabilities < minimum_total:
                total_vulnerabilities = minimum_total
                warnings.append(
                    "total_vulnerabilities was smaller than critical_issues + high_issues; normalized."
                )

        default_node_coverage, default_edge_coverage = self._calculate_plan_coverages(self.agent._test_plan)

        node_cov, err = self._resolve_coverage(
            kwargs.get("fsm_node_coverage"),
            fallback=default_node_coverage,
            field_name="fsm_node_coverage",
            warnings=warnings,
        )
        if err:
            return err
        edge_cov, err = self._resolve_coverage(
            kwargs.get("fsm_edge_coverage"),
            fallback=default_edge_coverage,
            field_name="fsm_edge_coverage",
            warnings=warnings,
        )
        if err:
            return err

        markdown_report = str(kwargs.get("markdown_report", "")).strip()
        if not markdown_report:
            markdown_report = self._build_fallback_markdown(
                status=status,
                total_vulnerabilities=total_vulnerabilities,
                critical_issues=critical_issues,
                high_issues=high_issues,
                node_cov=node_cov,
                edge_cov=edge_cov,
            )
            warnings.append("markdown_report missing, fallback markdown generated.")

        if status == "PASS" and total_vulnerabilities > 0:
            status = "CONDITIONAL"
            warnings.append("status PASS conflicts with vulnerabilities > 0; downgraded to CONDITIONAL.")

        report = AuditReportV1(
            status=status,
            game_url=self.agent._test_plan.game_url,
            total_vulnerabilities=total_vulnerabilities,
            critical_issues=critical_issues,
            high_issues=high_issues,
            fsm_node_coverage=node_cov,
            fsm_edge_coverage=edge_cov,
            plan=self.agent._test_plan,
            markdown_report=markdown_report,
        )

        # Save output in agent state so we can return it at the end of the run
        self.agent._final_report = report

        # We can also save it to workspace for persistence
        report_path = self.agent._workspace / "audit_report_v1.json"

        # Save to MemoryStore for cross-run history
        if hasattr(self.agent, "_memory") and self.agent._memory:
            await self.agent._memory.remember(
                content=report.model_dump_json(indent=2),
                tags=["game_audit", self.agent._test_plan.game_url],
            )

        report_path.write_text(report.model_dump_json(indent=2))
        if warnings:
            return (
                "Report successfully submitted and saved to memory. "
                f"The audit run is complete. Validation warnings: {' | '.join(warnings)}"
            )
        return "Report successfully submitted and saved to memory. The audit run is complete."

    def _normalize_status(self, value: Any) -> str | None:
        """Normalize status to PASS/FAIL/CONDITIONAL."""
        if value is None:
            return None
        normalized = str(value).strip().upper()
        if normalized in {"PASS", "FAIL", "CONDITIONAL"}:
            return normalized
        return None

    def _to_non_negative_int(self, value: Any, field_name: str) -> tuple[int, str | None]:
        """Convert value to a non-negative integer, returning (value, error)."""
        try:
            number = int(value)
        except (TypeError, ValueError):
            return 0, f"Error: {field_name} must be a non-negative integer."
        if number < 0:
            return 0, f"Error: {field_name} must be a non-negative integer."
        return number, None

    def _resolve_coverage(
        self,
        value: Any,
        *,
        fallback: float,
        field_name: str,
        warnings: list[str],
    ) -> tuple[float, str | None]:
        """Resolve coverage value with range validation and fallback."""
        if value is None:
            warnings.append(f"{field_name} missing, fallback to computed coverage.")
            return fallback, None
        try:
            coverage = float(value)
        except (TypeError, ValueError):
            return 0.0, f"Error: {field_name} must be a number between 0.0 and 1.0."
        if coverage < 0.0 or coverage > 1.0:
            return 0.0, f"Error: {field_name} must be between 0.0 and 1.0."
        return coverage, None

    def _calculate_plan_coverages(self, plan: TestPlan) -> tuple[float, float]:
        """Compute fallback node/edge coverage from current plan state."""
        if plan.nodes:
            visited = sum(1 for node in plan.nodes if node.is_visited)
            node_cov = visited / len(plan.nodes)
        else:
            node_cov = 0.0

        if plan.edges:
            traversed = sum(1 for edge in plan.edges if edge.is_traversed)
            edge_cov = traversed / len(plan.edges)
        else:
            edge_cov = 0.0
        return node_cov, edge_cov

    def _build_fallback_markdown(
        self,
        *,
        status: str,
        total_vulnerabilities: int,
        critical_issues: int,
        high_issues: int,
        node_cov: float,
        edge_cov: float,
    ) -> str:
        """Build minimal markdown when markdown_report is missing."""
        return (
            "# Game Audit Report\n\n"
            f"- Status: {status}\n"
            f"- Total Vulnerabilities: {total_vulnerabilities}\n"
            f"- Critical Issues: {critical_issues}\n"
            f"- High Issues: {high_issues}\n"
            f"- FSM Node Coverage: {node_cov:.2f}\n"
            f"- FSM Edge Coverage: {edge_cov:.2f}\n"
        )


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
            for node in self.agent._test_plan.nodes:
                for case in node.assertions:
                    if case.id == case_id:
                        node.is_visited = True
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
                "limit": {"type": "integer", "description": "Maximum number of past reports to return. Default is 5."},
                "mode": {
                    "type": "string",
                    "enum": ["summary", "full"],
                    "description": "summary returns compact regression-oriented digest; full returns raw report payloads."
                },
            },
            "required": ["game_url"]
        }

    async def execute(self, **kwargs: Any) -> str:
        if not hasattr(self.agent, "_memory") or not self.agent._memory:
            return "Error: Memory store is not available."

        game_url = kwargs["game_url"]
        mode = str(kwargs.get("mode", "summary")).lower()
        try:
            limit = int(kwargs.get("limit", 5))
        except (TypeError, ValueError):
            limit = 5
        limit = min(max(limit, 1), 20)

        # Search for exact game_url in tags or query
        query = f"game_audit {game_url}"
        memories = await self.agent._memory.recall(query=query, top_k=limit)

        if not memories:
            return f"No past reports found for {game_url}."

        reports = []
        parsed_reports: list[dict[str, Any]] = []
        for i, m in enumerate(memories):
            if mode == "full":
                reports.append(f"--- Past Report {i+1} ({m.created_at}) ---\n{m.content}")
                continue

            # summary mode
            try:
                report = json.loads(m.content)
                parsed_reports.append(report)
                failed_cases = self._extract_failed_case_ids(report)
                markdown_hint = str(report.get("markdown_report", "")).strip().replace("\n", " ")
                if len(markdown_hint) > 160:
                    markdown_hint = markdown_hint[:160] + "...[truncated]"
                reports.append(
                    f"--- Past Report {i+1} ({m.created_at}) ---\n"
                    f"status={report.get('status', 'UNKNOWN')}, "
                    f"issues(total/critical/high)="
                    f"{report.get('total_vulnerabilities', 0)}/"
                    f"{report.get('critical_issues', 0)}/"
                    f"{report.get('high_issues', 0)}, "
                    f"coverage(node/edge)="
                    f"{report.get('fsm_node_coverage', 0.0)}/"
                    f"{report.get('fsm_edge_coverage', 0.0)}\n"
                    f"failed_cases={', '.join(failed_cases) if failed_cases else '-'}\n"
                    f"report_hint={markdown_hint or '-'}"
                )
            except Exception:
                raw = str(m.content).strip().replace("\n", " ")
                if len(raw) > 160:
                    raw = raw[:160] + "...[truncated]"
                reports.append(
                    f"--- Past Report {i+1} ({m.created_at}) ---\n"
                    f"unparsed_content={raw}"
                )

        if not reports:
            return f"No valid past reports found for {game_url}."

        if mode == "full":
            return "\n\n".join(reports)

        persistent_failures = self._find_persistent_failures(parsed_reports)
        summary_header = (
            f"Historical summary for {game_url}\n"
            f"reports={len(reports)}\n"
            f"persistent_failures={', '.join(persistent_failures) if persistent_failures else '-'}"
        )
        return summary_header + "\n\n" + "\n\n".join(reports)

    def _extract_failed_case_ids(self, report: dict[str, Any]) -> list[str]:
        """Extract failed/pending-review case IDs from report payload."""
        failed: set[str] = set()
        plan = report.get("plan", {})

        for case in plan.get("test_cases", []):
            case_id = str(case.get("id", "")).strip()
            status = str(case.get("status", "")).upper()
            if case_id and status in {"FAILED", "PENDING_REVIEW"}:
                failed.add(case_id)

        for node in plan.get("nodes", []):
            for case in node.get("assertions", []):
                case_id = str(case.get("id", "")).strip()
                status = str(case.get("status", "")).upper()
                if case_id and status in {"FAILED", "PENDING_REVIEW"}:
                    failed.add(case_id)

        return sorted(failed)

    def _find_persistent_failures(self, reports: list[dict[str, Any]]) -> list[str]:
        """Find case IDs that fail across all parsed reports."""
        if not reports:
            return []
        failure_sets = [set(self._extract_failed_case_ids(r)) for r in reports]
        if not failure_sets:
            return []
        intersection = failure_sets[0]
        for failure_set in failure_sets[1:]:
            intersection = intersection.intersection(failure_set)
        return sorted(intersection)


class EvaluateRegressionGateTool(Tool):
    """Tool to evaluate release gate recommendation from history + current run."""

    def __init__(self, agent: Any) -> None:
        self.agent = agent

    @property
    def name(self) -> str:
        return "evaluate_regression_gate"

    @property
    def description(self) -> str:
        return (
            "Evaluate regression gate recommendation (PASS/CONDITIONAL/FAIL) based on "
            "historical persistent failures and current run findings."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "game_url": {"type": "string", "description": "The URL of the game."},
                "current_failed_cases": {
                    "type": "array",
                    "description": "Optional current-run failed/pending-review case IDs.",
                    "items": {"type": "string"},
                },
                "current_critical_issues": {"type": "integer", "description": "Current run critical issues."},
                "current_high_issues": {"type": "integer", "description": "Current run high issues."},
                "limit": {"type": "integer", "description": "How many historical reports to consider. Default 5."},
            },
            "required": ["game_url"],
        }

    async def execute(self, **kwargs: Any) -> str:
        game_url = kwargs["game_url"]
        current_failed_cases = self._normalize_case_ids(kwargs.get("current_failed_cases"))
        if not current_failed_cases:
            current_failed_cases = self._extract_current_failed_cases_from_plan()

        current_critical_issues = self._to_non_negative_int(kwargs.get("current_critical_issues", 0))
        current_high_issues = self._to_non_negative_int(kwargs.get("current_high_issues", 0))
        limit = min(max(self._to_non_negative_int(kwargs.get("limit", 5)) or 5, 1), 20)

        parsed_reports: list[dict[str, Any]] = []
        memory_enabled = bool(hasattr(self.agent, "_memory") and self.agent._memory)
        if memory_enabled:
            query = f"game_audit {game_url}"
            memories = await self.agent._memory.recall(query=query, top_k=limit)
            for memory in memories:
                try:
                    parsed_reports.append(json.loads(memory.content))
                except Exception:
                    continue

        helper = GetPastReportsTool(self.agent)
        persistent_failures = helper._find_persistent_failures(parsed_reports)
        unresolved_persistent = sorted(set(current_failed_cases).intersection(persistent_failures))

        score = 100
        score -= current_critical_issues * 25
        score -= current_high_issues * 12
        score -= len(current_failed_cases) * 6
        score -= len(unresolved_persistent) * 10
        score = max(0, min(100, score))

        recommendation = "PASS"
        if current_critical_issues > 0 or unresolved_persistent:
            recommendation = "FAIL"
        elif current_high_issues > 0 or current_failed_cases:
            recommendation = "CONDITIONAL"
        elif score < 70:
            recommendation = "CONDITIONAL"

        result = {
            "game_url": game_url,
            "recommendation": recommendation,
            "gate_score": score,
            "current_failed_cases": current_failed_cases,
            "current_critical_issues": current_critical_issues,
            "current_high_issues": current_high_issues,
            "persistent_failures": persistent_failures,
            "unresolved_persistent_failures": unresolved_persistent,
            "history_reports_considered": len(parsed_reports),
            "history_enabled": memory_enabled,
        }
        return "Regression gate evaluated.\n" + json.dumps(result, ensure_ascii=False, indent=2)

    def _normalize_case_ids(self, value: Any) -> list[str]:
        """Normalize case id list to unique sorted list."""
        if not isinstance(value, list):
            return []
        cleaned = {str(item).strip() for item in value if str(item).strip()}
        return sorted(cleaned)

    def _to_non_negative_int(self, value: Any) -> int:
        """Convert value to non-negative integer; invalid values fallback to 0."""
        try:
            number = int(value)
        except (TypeError, ValueError):
            return 0
        return max(0, number)

    def _extract_current_failed_cases_from_plan(self) -> list[str]:
        """Extract failed/pending-review case IDs from current in-memory plan."""
        if not hasattr(self.agent, "_test_plan") or not self.agent._test_plan:
            return []
        plan = self.agent._test_plan
        failed: set[str] = set()

        for case in plan.test_cases:
            if case.status in {TestCaseStatus.FAILED, TestCaseStatus.PENDING_REVIEW}:
                failed.add(case.id)

        for node in plan.nodes:
            for case in node.assertions:
                if case.status in {TestCaseStatus.FAILED, TestCaseStatus.PENDING_REVIEW}:
                    failed.add(case.id)

        return sorted(failed)
