"""Audit logging for all control plane operations."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


class AuditLog:
    """
    Records all scheduling decisions, agent executions, validations, and tool calls.

    Provides a complete audit trail for debugging, compliance, and analysis.
    """

    def __init__(self, data_dir: Path) -> None:
        self.log_dir = data_dir / "audit"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _log_file(self) -> Path:
        """Get today's audit log file."""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.log_dir / f"{today}.jsonl"

    def _write(self, entry: dict[str, Any]) -> None:
        """Write an audit entry."""
        entry["timestamp"] = datetime.now().isoformat()
        with open(self._log_file(), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    @staticmethod
    def _preview(value: Any, limit: int = 200) -> str:
        """Serialize a value for compact audit logging."""
        if isinstance(value, str):
            text = value
        else:
            try:
                text = json.dumps(value, ensure_ascii=False)
            except TypeError:
                text = str(value)
        return text[:limit]

    def log_dispatch(
        self,
        session_key: str,
        message: str,
        agent_name: str,
        task_description: str,
        request_id: str = "",
    ) -> None:
        """Log a scheduling dispatch decision."""
        self._write(
            {
                "type": "dispatch",
                "request_id": request_id,
                "session_key": session_key,
                "message_preview": message[:200],
                "target_agent": agent_name,
                "task_description": task_description,
            }
        )
        logger.debug(f"Audit: dispatch to {agent_name} for session {session_key}")

    def log_execution(
        self,
        session_key: str,
        agent_name: str,
        result_preview: str,
        duration_ms: float,
        success: bool = True,
        request_id: str = "",
    ) -> None:
        """Log a sub-agent execution result."""
        self._write(
            {
                "type": "execution",
                "request_id": request_id,
                "session_key": session_key,
                "agent_name": agent_name,
                "result_preview": result_preview[:200],
                "duration_ms": round(duration_ms, 2),
                "success": success,
            }
        )
        status = "ok" if success else "failed"
        logger.debug(f"Audit: {agent_name} execution {status} ({duration_ms:.0f}ms)")

    def log_validation(
        self,
        session_key: str,
        agent_name: str,
        passed: bool,
        reason: str = "",
        request_id: str = "",
        severity: str = "info",
        policy_id: str = "",
        redactions: list[str] | None = None,
    ) -> None:
        """Log a validation result."""
        self._write(
            {
                "type": "validation",
                "request_id": request_id,
                "session_key": session_key,
                "agent_name": agent_name,
                "passed": passed,
                "reason": reason,
                "severity": severity,
                "policy_id": policy_id,
                "redactions": redactions or [],
            }
        )
        if not passed:
            logger.warning(f"Audit: validation failed for {agent_name} - {reason}")

    def log_tool_call(
        self,
        session_key: str,
        agent_name: str,
        tool_name: str,
        params: dict[str, Any],
        result_preview: str,
        duration_ms: float,
        success: bool,
        request_id: str = "",
    ) -> None:
        """Log one tool invocation from a sub-agent."""
        self._write(
            {
                "type": "tool_call",
                "request_id": request_id,
                "session_key": session_key,
                "agent_name": agent_name,
                "tool_name": tool_name,
                "params_preview": self._preview(params),
                "result_preview": self._preview(result_preview),
                "duration_ms": round(duration_ms, 2),
                "success": success,
            }
        )
