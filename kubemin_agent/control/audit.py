"""Audit logging for all control plane operations."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from loguru import logger


class AuditLog:
    """
    Records all scheduling decisions, agent executions, validations, and tool calls.

    Provides a complete audit trail for debugging, compliance, and analysis.
    """

    def __init__(
        self,
        data_dir: Path,
        retention_days: int = 30,
        file_max_mb: int = 50,
    ) -> None:
        self.log_dir = data_dir / "audit"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._retention_days = max(1, retention_days)
        self._file_max_bytes = max(1, file_max_mb) * 1024 * 1024
        self._last_cleanup_day: date = datetime.now().date()
        self._cleanup_old_logs()

    def _log_file(self) -> Path:
        """Get today's audit log file."""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.log_dir / f"{today}.jsonl"

    def _write(self, entry: dict[str, Any]) -> None:
        """Write an audit entry."""
        entry["timestamp"] = datetime.now().isoformat()
        self._maybe_cleanup_old_logs()
        serialized = json.dumps(entry, ensure_ascii=False)
        self._rotate_active_log_if_needed(additional_bytes=len(serialized.encode("utf-8")) + 1)
        with open(self._log_file(), "a", encoding="utf-8") as f:
            f.write(serialized + "\n")

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
        task_id: str = "",
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
                "task_id": task_id,
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
        task_id: str = "",
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
                "task_id": task_id,
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
        task_id: str = "",
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
                "task_id": task_id,
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
        task_id: str = "",
        request_id: str = "",
    ) -> None:
        """Log one tool invocation from a sub-agent."""
        self._write(
            {
                "type": "tool_call",
                "request_id": request_id,
                "session_key": session_key,
                "agent_name": agent_name,
                "task_id": task_id,
                "tool_name": tool_name,
                "params_preview": self._preview(params),
                "result_preview": self._preview(result_preview),
                "duration_ms": round(duration_ms, 2),
                "success": success,
            }
        )

    def log_reasoning_step(
        self,
        session_key: str,
        agent_name: str,
        task_id: str,
        step_index: int,
        phase: str,
        intent_summary: str,
        action: str,
        observation_summary: str,
        confidence: float | None = None,
        error: str = "",
        request_id: str = "",
    ) -> None:
        """Log one structured reasoning step from a sub-agent run."""
        self._write(
            {
                "type": "reasoning_step",
                "request_id": request_id,
                "session_key": session_key,
                "agent_name": agent_name,
                "task_id": task_id,
                "step_index": step_index,
                "phase": phase,
                "intent_summary": self._preview(intent_summary),
                "action": self._preview(action),
                "observation_summary": self._preview(observation_summary),
                "confidence": confidence,
                "error": self._preview(error),
            }
        )

    def log_evaluation(
        self,
        session_key: str,
        agent_name: str,
        task_id: str,
        overall_score: int,
        dimension_scores: dict[str, int],
        passed: bool,
        warn_threshold: int,
        reasons: list[str] | None = None,
        suggestions: list[str] | None = None,
        request_id: str = "",
    ) -> None:
        """Log an execution evaluation result."""
        self._write(
            {
                "type": "evaluation",
                "request_id": request_id,
                "session_key": session_key,
                "agent_name": agent_name,
                "task_id": task_id,
                "overall_score": overall_score,
                "dimension_scores": dimension_scores,
                "passed": passed,
                "warn_threshold": warn_threshold,
                "reasons": reasons or [],
                "suggestions": suggestions or [],
            }
        )

    def _rotate_active_log_if_needed(self, additional_bytes: int) -> None:
        """Rotate today's log file when it exceeds max size."""
        active_file = self._log_file()
        if not active_file.exists():
            return
        projected_size = active_file.stat().st_size + additional_bytes
        if projected_size <= self._file_max_bytes:
            return
        rotated_file = self._next_rotated_path(active_file)
        active_file.rename(rotated_file)
        logger.info(f"Audit log rotated: {rotated_file.name}")

    @staticmethod
    def _next_rotated_path(active_file: Path) -> Path:
        """Generate a non-conflicting rotated log path."""
        suffix = datetime.now().strftime("%H%M%S")
        candidate = active_file.with_name(f"{active_file.stem}.{suffix}.jsonl")
        index = 1
        while candidate.exists():
            candidate = active_file.with_name(f"{active_file.stem}.{suffix}.{index}.jsonl")
            index += 1
        return candidate

    def _maybe_cleanup_old_logs(self) -> None:
        """Run retention cleanup once per day."""
        today = datetime.now().date()
        if today == self._last_cleanup_day:
            return
        self._cleanup_old_logs()
        self._last_cleanup_day = today

    def _cleanup_old_logs(self) -> None:
        """Delete audit log files older than retention period."""
        cutoff = datetime.now() - timedelta(days=self._retention_days)
        for path in self.log_dir.glob("*.jsonl"):
            try:
                modified_at = datetime.fromtimestamp(path.stat().st_mtime)
                if modified_at < cutoff:
                    path.unlink()
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Failed to cleanup audit log {path}: {e}")
