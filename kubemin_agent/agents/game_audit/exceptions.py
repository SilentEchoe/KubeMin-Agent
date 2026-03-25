"""Exceptions used by GameAuditAgent."""


class SuspendExecutionError(Exception):
    """Raised when the agent requests human review, suspending the run loop."""

    def __init__(self, reason: str, case_id: str, screenshot_path: str = "") -> None:
        super().__init__(f"Audit suspended pending human review: {reason}")
        self.reason = reason
        self.case_id = case_id
        self.screenshot_path = screenshot_path


# Backward-compatible alias for callers still using the old name.
SuspendExecutionException = SuspendExecutionError
