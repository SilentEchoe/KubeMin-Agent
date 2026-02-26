"""ChromaDB vector database memory backend."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from kubemin_agent.agent.memory.backend import MemoryBackend
from kubemin_agent.agent.memory.entry import MemoryEntry


class ChromaDBBackend(MemoryBackend):
    """
    Memory backend using ChromaDB for semantic search.

    Provides true retrieval-augmented generation (RAG) capabilities
    by embedding memory contents and performing vector similarity search.
    """

    def __init__(self, memory_dir: Path) -> None:
        """
        Initialize the ChromaDB backend.

        Args:
            memory_dir: Directory to persistently store the vector database.
        """
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError:
            raise RuntimeError(
                "chromadb is required for this backend. Install it with: "
                "pip install chromadb"
            )

        self._db_path = memory_dir / "chroma_db"
        self._db_path.mkdir(parents=True, exist_ok=True)

        logger.debug(f"Initializing ChromaDB client at {self._db_path}")

        # Local persistent client
        self._client = chromadb.PersistentClient(
            path=str(self._db_path),
            settings=Settings(anonymized_telemetry=False),
        )

        # Get or create the main memory collection
        self._collection = self._client.get_or_create_collection(
            name="agent_memory",
            metadata={"description": "KubeMin Agent memory collection"},
        )

    async def store(self, entry: MemoryEntry) -> str:
        """Store a memory entry in ChromaDB."""
        # Clean metadata dictionary (Chroma accepts str, int, float, bool)
        metadata: dict[str, Any] = {
            "source": entry.source or "",
            "created_at": entry.created_at.isoformat(),
        }

        # Chroma doesn't support list metadata directly in older versions,
        # but we can store it as a comma-separated string
        if entry.tags:
            metadata["tags"] = ",".join(entry.tags)

        # upsert handles both insert and update gracefully
        self._collection.upsert(
            documents=[entry.content],
            metadatas=[metadata],
            ids=[entry.id],
        )

        logger.debug(f"ChromaDBBackend: stored entry {entry.id}")
        return entry.id

    async def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        """Search memory semantically using vector similarity."""
        if not query.strip():
            # Chroma requires a non-empty query string for semantic search.
            # If empty, just return the most recent entries.
            return (await self.list_all())[:top_k]

        count = self._collection.count()
        if count == 0:
            return []

        # Ensure we don't request more results than documents exist
        fetch_k = min(top_k, count)

        results = self._collection.query(
            query_texts=[query],
            n_results=fetch_k,
        )

        # Chroma returns lists of lists because it supports batch queries
        if not results or not results["ids"] or not results["ids"][0]:
            return []

        ids = results["ids"][0]
        documents = results["documents"][0] if results.get("documents") else []
        metadatas = results["metadatas"][0] if results.get("metadatas") else []

        entries: list[MemoryEntry] = []
        for i in range(len(ids)):
            doc_id = ids[i]
            # Handle potential None values safely
            content = documents[i] if len(documents) > i and documents[i] else ""
            meta = metadatas[i] if len(metadatas) > i and metadatas[i] else {}

            try:
                from datetime import datetime
                created_at = datetime.now()
                if "created_at" in meta:
                    try:
                        created_at = datetime.fromisoformat(str(meta["created_at"]))
                    except ValueError:
                        pass

                tags = []
                if "tags" in meta and meta["tags"]:
                    tags = [t.strip() for t in str(meta["tags"]).split(",") if t.strip()]

                entries.append(
                    MemoryEntry(
                        id=doc_id,
                        content=str(content),
                        tags=tags,
                        source=str(meta.get("source", "")),
                        created_at=created_at,
                    )
                )
            except Exception as e:
                logger.warning(f"ChromaDBBackend: failed to parse search result {doc_id}: {e}")

        return entries

    async def delete(self, entry_id: str) -> bool:
        """Delete an entry by ID."""
        try:
            # Check if it exists (by trying to get it)
            existing = self._collection.get(ids=[entry_id])
            if not existing or not existing["ids"]:
                return False

            self._collection.delete(ids=[entry_id])
            logger.debug(f"ChromaDBBackend: deleted entry {entry_id}")
            return True
        except Exception as e:
            logger.warning(f"ChromaDBBackend: failed to delete {entry_id}: {e}")
            return False

    async def list_all(self) -> list[MemoryEntry]:
        """List all entries (useful but potentially expensive for large collections)."""
        count = self._collection.count()
        if count == 0:
            return []

        # Get all documents (may be slow if DB is huge, but fine for agent local store)
        results = self._collection.get()

        if not results or not results["ids"]:
            return []

        ids = results["ids"]
        documents = results["documents"] or []
        metadatas = results["metadatas"] or []

        entries: list[MemoryEntry] = []
        for i in range(len(ids)):
            doc_id = ids[i]
            content = documents[i] if len(documents) > i and documents[i] else ""
            meta = metadatas[i] if len(metadatas) > i and metadatas[i] else {}

            from datetime import datetime
            created_at = datetime.now()
            if "created_at" in meta:
                try:
                    created_at = datetime.fromisoformat(str(meta["created_at"]))
                except ValueError:
                    pass

            tags = []
            if "tags" in meta and meta["tags"]:
                tags = [t.strip() for t in str(meta["tags"]).split(",") if t.strip()]

            entries.append(
                MemoryEntry(
                    id=doc_id,
                    content=str(content),
                    tags=tags,
                    source=str(meta.get("source", "")),
                    created_at=created_at,
                )
            )

        # Sort newest first
        entries.sort(key=lambda e: e.created_at, reverse=True)
        return entries
