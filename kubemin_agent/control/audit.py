"""Audit logging for all control plane operations."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


class AuditLog:
    """
    Records all scheduling decisions, agent executions, and validations.

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

    def log_dispatch(
        self,
        session_key: str,
        message: str,
        agent_name: str,
        task_description: str,
    ) -> None:
        """Log a scheduling dispatch decision."""
        self._write({
            "type": "dispatch",
            "session_key": session_key,
            "message_preview": message[:200],
            "target_agent": agent_name,
            "task_description": task_description,
        })
        logger.debug(f"Audit: dispatch to {agent_name} for session {session_key}")

    def log_execution(
        self,
        session_key: str,
        agent_name: str,
        result_preview: str,
        duration_ms: float,
        success: bool = True,
    ) -> None:
        """Log a sub-agent execution result."""
        self._write({
            "type": "execution",
            "session_key": session_key,
            "agent_name": agent_name,
            "result_preview": result_preview[:200],
            "duration_ms": round(duration_ms, 2),
            "success": success,
        })
        logger.debug(f"Audit: {agent_name} execution {'ok' if success else 'failed'} ({duration_ms:.0f}ms)")

    def log_validation(
        self,
        session_key: str,
        agent_name: str,
        passed: bool,
        reason: str = "",
    ) -> None:
        """Log a validation result."""
        self._write({
            "type": "validation",
            "session_key": session_key,
            "agent_name": agent_name,
            "passed": passed,
            "reason": reason,
        })
        if not passed:
            logger.warning(f"Audit: validation failed for {agent_name} - {reason}")
