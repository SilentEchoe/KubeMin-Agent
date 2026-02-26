"""MemoryStore -- unified facade for memory operations."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from loguru import logger

from kubemin_agent.agent.memory.backend import MemoryBackend
from kubemin_agent.agent.memory.entry import MemoryEntry


class MemoryStore:
    """
    Unified facade for agent memory operations.

    Delegates all storage to a pluggable MemoryBackend.
    Upper layers (ContextBuilder, agents) depend only on this class.
    """

    def __init__(self, backend: MemoryBackend) -> None:
        self._backend = backend

    @classmethod
    def create(cls, workspace: Path, backend_type: str = "file") -> MemoryStore:
        """
        Factory method to create a MemoryStore with a specific backend.

        Args:
            workspace: Workspace root path.
            backend_type: Backend type: 'file', 'jsonl', or 'chroma'.

        Returns:
            Configured MemoryStore instance.
        """
        memory_dir = workspace / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)

        if backend_type == "chroma":
            from kubemin_agent.agent.memory.chroma_backend import ChromaDBBackend
            backend = ChromaDBBackend(memory_dir)
        elif backend_type == "jsonl":
            from kubemin_agent.agent.memory.jsonl_backend import JSONLBackend
            backend = JSONLBackend(memory_dir)
        else:
            from kubemin_agent.agent.memory.file_backend import FileBackend
            backend = FileBackend(memory_dir)

        logger.debug(f"MemoryStore created with {backend_type} backend")
        return cls(backend)

    async def remember(
        self,
        content: str,
        tags: list[str] | None = None,
        source: str = "",
    ) -> str:
        """
        Store a new memory.

        Args:
            content: Memory content text.
            tags: Optional tags for categorization.
            source: Origin identifier (agent name, session key).

        Returns:
            The generated entry ID.
        """
        entry = MemoryEntry(
            id=uuid4().hex[:12],
            content=content,
            tags=tags or [],
            source=source,
        )
        return await self._backend.store(entry)

    async def recall(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        """
        Retrieve relevant memories for a query.

        Args:
            query: Search query text.
            top_k: Maximum number of results.

        Returns:
            List of relevant MemoryEntry objects.
        """
        return await self._backend.search(query, top_k)

    async def forget(self, entry_id: str) -> bool:
        """
        Delete a memory by ID.

        Args:
            entry_id: ID of the memory to delete.

        Returns:
            True if deleted, False if not found.
        """
        return await self._backend.delete(entry_id)

    async def list_all(self) -> list[MemoryEntry]:
        """List all stored memories."""
        return await self._backend.list_all()

    async def get_context(self, query: str = "", top_k: int = 5) -> str:
        """
        Get memory context formatted for the system prompt.

        If a query is provided, retrieves relevant memories via search.
        If no query is provided, returns all memories (capped at top_k).

        Args:
            query: Optional search query for relevance filtering.
            top_k: Maximum number of memories to include.

        Returns:
            Formatted memory context string.
        """
        if query:
            entries = await self.recall(query, top_k)
        else:
            entries = (await self.list_all())[:top_k]

        if not entries:
            return ""

        parts: list[str] = []
        for entry in entries:
            tag_str = f" [{', '.join(entry.tags)}]" if entry.tags else ""
            timestamp = entry.created_at.strftime("%Y-%m-%d %H:%M")
            parts.append(f"- ({timestamp}{tag_str}) {entry.content}")

        return "## Relevant Memories\n\n" + "\n".join(parts)
