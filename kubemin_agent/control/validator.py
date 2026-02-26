"""Validator for sub-agent output verification."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from loguru import logger


# Dangerous command patterns to intercept
DANGEROUS_PATTERNS = [
    r"\brm\s+-rf\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\b:\(\)\{ :\|:& \};:",
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

K8S_MUTATING_PATTERNS = [
    r"\bkubectl\s+create\b",
    r"\bkubectl\s+replace\b",
    r"\bkubectl\s+run\b",
    r"\bkubectl\s+set\b",
    r"\bkubectl\s+rollout\b",
]

# Basic secret formats to redact from outputs.
SECRET_PATTERNS = {
    "secret.bearer": re.compile(r"(?i)(\bBearer\s+)([A-Za-z0-9\-._~+/]+=*)"),
    "secret.kv": re.compile(
        r"(?i)(\b(?:api[_-]?key|token|secret|password)\b\s*[:=]\s*)([^\s,;]{6,})"
    ),
}


@dataclass
class ValidationResult:
    """Result of a validation check."""

    passed: bool
    reason: str = ""
    severity: str = "info"
    policy_id: str = ""
    redactions: list[str] = field(default_factory=list)
    sanitized_result: str = ""


class Validator:
    """
    Validates sub-agent output for safety and quality.

    Intercepts dangerous operations, checks output quality,
    redacts basic sensitive strings, and enforces security policies.
    """

    def __init__(self) -> None:
        self._dangerous_patterns = [re.compile(p, re.IGNORECASE) for p in DANGEROUS_PATTERNS]
        self._k8s_mutating_patterns = [
            re.compile(p, re.IGNORECASE) for p in K8S_MUTATING_PATTERNS
        ]

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
        sanitized, redactions = self.redact_sensitive(result)

        is_safe, policy_id = self.check_safety(agent_name, sanitized)
        if not is_safe:
            return ValidationResult(
                passed=False,
                reason="Output contains dangerous commands or policy violations",
                severity="block",
                policy_id=policy_id,
                redactions=redactions,
                sanitized_result=sanitized,
            )

        if not self.check_quality(sanitized):
            return ValidationResult(
                passed=False,
                reason="Output is empty or malformed",
                severity="warn",
                policy_id="quality.empty",
                redactions=redactions,
                sanitized_result=sanitized,
            )

        return ValidationResult(
            passed=True,
            severity="info",
            policy_id="ok",
            redactions=redactions,
            sanitized_result=sanitized,
        )

    def redact_sensitive(self, result: str) -> tuple[str, list[str]]:
        """
        Redact sensitive strings from model output.

        Returns:
            Tuple of (sanitized_text, redaction_policy_ids).
        """
        sanitized = result
        redactions: list[str] = []

        for policy_id, pattern in SECRET_PATTERNS.items():
            before = sanitized
            sanitized = pattern.sub(r"\1[REDACTED]", sanitized)
            if sanitized != before:
                redactions.append(policy_id)

        if redactions:
            logger.warning(f"Sensitive content redacted by validator: {sorted(set(redactions))}")

        return sanitized, sorted(set(redactions))

    def check_safety(self, agent_name: str, result: str) -> tuple[bool, str]:
        """
        Check if output contains dangerous patterns.

        Returns:
            Tuple (is_safe, policy_id).
        """
        for pattern in self._dangerous_patterns:
            if pattern.search(result):
                logger.warning(f"Dangerous pattern detected: {pattern.pattern}")
                return False, "safety.dangerous_pattern"

        if agent_name == "k8s":
            for pattern in self._k8s_mutating_patterns:
                if pattern.search(result):
                    logger.warning(f"K8s mutating command detected: {pattern.pattern}")
                    return False, "safety.k8s_mutating"

        return True, "ok"

    def check_quality(self, result: str) -> bool:
        """
        Check basic output quality.

        Returns:
            True if output meets minimum quality standards.
        """
        if not result or not result.strip():
            return False
        return True
