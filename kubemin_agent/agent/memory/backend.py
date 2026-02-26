"""Abstract base class for memory storage backends."""

from __future__ import annotations

from abc import ABC, abstractmethod

from kubemin_agent.agent.memory.entry import MemoryEntry


class MemoryBackend(ABC):
    """
    Abstract memory storage backend.

    All memory backends must implement this interface.
    This allows MemoryStore to work with any storage mechanism
    (files, JSONL, vector databases, etc.) without code changes.
    """

    @abstractmethod
    async def store(self, entry: MemoryEntry) -> str:
        """
        Store a memory entry.

        Args:
            entry: The memory entry to store.

        Returns:
            The entry ID.
        """

    @abstractmethod
    async def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        """
        Search for relevant memories.

        Args:
            query: Search query text.
            top_k: Maximum number of results to return.

        Returns:
            List of matching memory entries, ordered by relevance.
        """

    @abstractmethod
    async def delete(self, entry_id: str) -> bool:
        """
        Delete a memory entry by ID.

        Args:
            entry_id: ID of the entry to delete.

        Returns:
            True if deleted, False if not found.
        """

    @abstractmethod
    async def list_all(self) -> list[MemoryEntry]:
        """
        List all stored memory entries.

        Returns:
            All memory entries, ordered by creation time (newest first).
        """
