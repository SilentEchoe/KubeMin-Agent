"""Validator for sub-agent output verification."""

import re
from dataclasses import dataclass

from loguru import logger


# Dangerous command patterns to intercept
DANGEROUS_PATTERNS = [
    r"\brm\s+-rf\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\b:(){ :|:& };:",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bkubectl\s+delete\b",
    r"\bkubectl\s+apply\b",
    r"\bkubectl\s+patch\b",
    r"\bkubectl\s+edit\b",
    r"\bkubectl\s+scale\b",
    r"\bkubectl\s+drain\b",
    r"\bkubectl\s+cordon\b",
    r"\bkubectl\s+taint\b",
]


@dataclass
class ValidationResult:
    """Result of a validation check."""

    passed: bool
    reason: str = ""


class Validator:
    """
    Validates sub-agent output for safety and quality.

    Intercepts dangerous operations, checks output quality,
    and enforces security policies.
    """

    def __init__(self) -> None:
        self._dangerous_patterns = [re.compile(p, re.IGNORECASE) for p in DANGEROUS_PATTERNS]

    async def validate(
        self,
        agent_name: str,
        result: str,
        context: dict | None = None,
    ) -> ValidationResult:
        """
        Validate a sub-agent's output.

        Args:
            agent_name: Name of the agent that produced the result.
            result: The agent's output to validate.
            context: Optional context for validation.

        Returns:
            ValidationResult indicating pass/fail with reason.
        """
        # Safety check
        if not self.check_safety(result):
            return ValidationResult(
                passed=False,
                reason="Output contains dangerous commands or patterns",
            )

        # Quality check
        if not self.check_quality(result):
            return ValidationResult(
                passed=False,
                reason="Output is empty or malformed",
            )

        return ValidationResult(passed=True)

    def check_safety(self, result: str) -> bool:
        """
        Check if the output contains dangerous patterns.

        Returns:
            True if safe, False if dangerous patterns detected.
        """
        for pattern in self._dangerous_patterns:
            if pattern.search(result):
                logger.warning(f"Dangerous pattern detected: {pattern.pattern}")
                return False
        return True

    def check_quality(self, result: str) -> bool:
        """
        Check basic output quality.

        Returns:
            True if output meets minimum quality standards.
        """
        if not result or not result.strip():
            return False
        return True
