"""Subagent manager for background task execution."""

import asyncio
from typing import Any

from loguru import logger


class SubagentManager:
    """
    Manages background subagent tasks.

    Allows spawning async tasks that run independently and report
    results back to the main session.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}

    async def spawn(
        self,
        name: str,
        coro: Any,
    ) -> str:
        """
        Spawn a background task.

        Args:
            name: Task identifier.
            coro: Coroutine to execute.

        Returns:
            Task ID.
        """
        if name in self._tasks and not self._tasks[name].done():
            return f"Task '{name}' is already running"

        task = asyncio.create_task(coro, name=name)
        self._tasks[name] = task
        logger.info(f"Subagent spawned: {name}")
        return f"Task '{name}' started"

    def get_status(self, name: str) -> str:
        """Get the status of a background task."""
        task = self._tasks.get(name)
        if not task:
            return "not_found"
        if task.done():
            if task.exception():
                return "failed"
            return "completed"
        return "running"

    def list_tasks(self) -> dict[str, str]:
        """List all tasks with their status."""
        return {name: self.get_status(name) for name in self._tasks}

    async def cancel(self, name: str) -> bool:
        """Cancel a running task."""
        task = self._tasks.get(name)
        if not task or task.done():
            return False
        task.cancel()
        logger.info(f"Subagent cancelled: {name}")
        return True

    async def cleanup(self) -> None:
        """Cancel all running tasks."""
        for name, task in self._tasks.items():
            if not task.done():
                task.cancel()
                logger.debug(f"Cleaned up task: {name}")
        self._tasks.clear()
