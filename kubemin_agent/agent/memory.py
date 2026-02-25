"""Persistent memory store for the agent."""

from datetime import datetime
from pathlib import Path

from loguru import logger


class MemoryStore:
    """
    File-based persistent memory.

    Manages long-term memory (MEMORY.md) and daily notes (YYYY-MM-DD.md).
    """

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.memory_dir = workspace / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    @property
    def memory_file(self) -> Path:
        """Path to long-term memory file."""
        return self.memory_dir / "MEMORY.md"

    @property
    def today_file(self) -> Path:
        """Path to today's daily note."""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.memory_dir / f"{today}.md"

    def get_memory_context(self) -> str:
        """
        Get combined memory context for the system prompt.

        Returns:
            Combined long-term and today's memory.
        """
        parts: list[str] = []

        if self.memory_file.exists():
            content = self.memory_file.read_text(encoding="utf-8").strip()
            if content:
                parts.append(f"## Long-term Memory\n\n{content}")

        if self.today_file.exists():
            content = self.today_file.read_text(encoding="utf-8").strip()
            if content:
                parts.append(f"## Today's Notes\n\n{content}")

        return "\n\n".join(parts)

    def save_memory(self, content: str) -> None:
        """
        Save content to long-term memory.

        Args:
            content: Content to save.
        """
        self.memory_file.write_text(content, encoding="utf-8")
        logger.debug("Long-term memory updated")

    def append_daily(self, content: str) -> None:
        """
        Append content to today's daily note.

        Args:
            content: Content to append.
        """
        with open(self.today_file, "a", encoding="utf-8") as f:
            f.write(f"\n{content}\n")
        logger.debug("Daily note updated")
