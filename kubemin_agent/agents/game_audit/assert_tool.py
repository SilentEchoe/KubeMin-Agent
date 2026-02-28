"""Assertion tool for GameAuditAgent."""

from typing import Any

from kubemin_agent.agent.tools.base import Tool


class AssertTool(Tool):
    """Tool to perform logical and numeric assertions."""

    @property
    def name(self) -> str:
        return "run_assertion"

    @property
    def description(self) -> str:
        return (
            "Use this tool to evaluate deterministic assertions comparing expected and actual states. "
            "Supported assertion types: "
            "'assert_equal' (strict equality), 'assert_not_equal' (inequality), "
            "'assert_contains' (substring/item presence), and 'assert_delta' (numeric difference)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "assertion_type": {
                    "type": "string",
                    "enum": ["assert_equal", "assert_not_equal", "assert_contains", "assert_delta"],
                    "description": "The type of assertion to execute."
                },
                "expected": {
                    "type": "string",
                    "description": "The expected value. For assert_delta, this should be the expected difference (e.g., '-10')."
                },
                "actual": {
                    "type": "string",
                    "description": "The actual value observed. For assert_delta, this should represent the difference calculated (e.g., new_val - old_val)."
                }
            },
            "required": ["assertion_type", "expected", "actual"]
        }

    def _to_float(self, val: str) -> float | None:
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    async def execute(self, **kwargs: Any) -> str:
        assert_type = kwargs["assertion_type"]
        expected_str = str(kwargs["expected"])
        actual_str = str(kwargs["actual"])

        if assert_type == "assert_equal":
            if expected_str.strip() == actual_str.strip():
                return f"PASS: '{actual_str}' equals '{expected_str}'"
            return f"FAIL: Expected '{expected_str}', but got '{actual_str}'"

        elif assert_type == "assert_not_equal":
            if expected_str.strip() != actual_str.strip():
                return f"PASS: '{actual_str}' does not equal '{expected_str}'"
            return f"FAIL: Value uniquely equals '{expected_str}'"

        elif assert_type == "assert_contains":
            if expected_str in actual_str:
                return f"PASS: '{actual_str}' contains '{expected_str}'"
            return f"FAIL: '{actual_str}' does not contain '{expected_str}'"

        elif assert_type == "assert_delta":
            exp_num = self._to_float(expected_str)
            act_num = self._to_float(actual_str)
            if exp_num is None or act_num is None:
                return f"FAIL: assert_delta requires numeric inputs, got expected='{expected_str}', actual='{actual_str}'"
            
            # Using a very small epsilon for JS float comparison issues
            if abs(exp_num - act_num) < 1e-5:
                return f"PASS: calculated delta {act_num} matches expected delta {exp_num}"
            return f"FAIL: Expected delta of {exp_num}, but computed delta was {act_num}"

        return f"Error: Unknown assertion type '{assert_type}'"
