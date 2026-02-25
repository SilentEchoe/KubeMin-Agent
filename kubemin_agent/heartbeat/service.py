"""Heartbeat service for proactive agent wake-up."""

import asyncio
from pathlib import Path

from loguru import logger


class HeartbeatService:
    """
    Periodically checks for tasks and wakes the agent proactively.

    Reads a HEARTBEAT.md file from the workspace. If it contains tasks,
    triggers the agent to process them.
    """

    HEARTBEAT_OK = "HEARTBEAT_OK"

    def __init__(self, workspace: Path, interval_seconds: int = 1800) -> None:
        self.workspace = workspace
        self.interval = interval_seconds
        self.heartbeat_file = workspace / "HEARTBEAT.md"
        self._running = False

    async def run(self, execute_callback) -> None:
        """
        Run the heartbeat service loop.

        Args:
            execute_callback: Async callback to execute when tasks are found.
        """
        self._running = True
        logger.info(f"Heartbeat service started (interval: {self.interval}s)")

        while self._running:
            await asyncio.sleep(self.interval)

            if not self._running:
                break

            try:
                content = self._read_heartbeat()
                if content and content.strip() != self.HEARTBEAT_OK:
                    logger.info("Heartbeat: tasks found, triggering agent")
                    await execute_callback(content)
            except Exception as e:
                logger.error(f"Heartbeat check failed: {e}")

    def _read_heartbeat(self) -> str:
        """Read the heartbeat file content."""
        if not self.heartbeat_file.exists():
            return ""
        return self.heartbeat_file.read_text(encoding="utf-8").strip()

    def stop(self) -> None:
        """Stop the heartbeat service."""
        self._running = False
        logger.info("Heartbeat service stopped")
