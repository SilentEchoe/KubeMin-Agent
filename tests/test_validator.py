"""Tests for validator policies and redaction."""

import pytest

from kubemin_agent.control.validator import Validator


@pytest.mark.asyncio
async def test_validator_redacts_sensitive_values() -> None:
    validator = Validator()

    result = (
        "token = abcdef123456\n"
        "Authorization: Bearer very-secret-token-value\n"
        "Everything else is safe."
    )
    validation = await validator.validate("general", result)

    assert validation.passed is True
    assert "[REDACTED]" in validation.sanitized_result
    assert "abcdef123456" not in validation.sanitized_result
    assert "very-secret-token-value" not in validation.sanitized_result
    assert validation.redactions


@pytest.mark.asyncio
async def test_validator_blocks_mutating_k8s_commands() -> None:
    validator = Validator()
    validation = await validator.validate("k8s", "Please run: kubectl apply -f deploy.yaml")

    assert validation.passed is False
    assert validation.severity == "block"
    assert validation.policy_id.startswith("safety")
