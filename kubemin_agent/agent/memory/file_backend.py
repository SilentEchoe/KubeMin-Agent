"""File-based memory backend using individual .md files."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from kubemin_agent.agent.memory.backend import MemoryBackend
from kubemin_agent.agent.memory.entry import MemoryEntry


class FileBackend(MemoryBackend):
    """
    Memory backend that stores each entry as an individual .md file.

    Search is implemented via simple keyword substring matching.
    Suitable for development, testing, and small-scale usage.
    """

    def __init__(self, memory_dir: Path) -> None:
        self._dir = memory_dir / "entries"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _entry_path(self, entry_id: str) -> Path:
        return self._dir / f"{entry_id}.md"

    async def store(self, entry: MemoryEntry) -> str:
        path = self._entry_path(entry.id)

        # Front-matter style header + content
        lines = [
            f"<!-- id: {entry.id} -->",
            f"<!-- created_at: {entry.created_at.isoformat()} -->",
            f"<!-- source: {entry.source} -->",
            f"<!-- tags: {','.join(entry.tags)} -->",
            "",
            entry.content,
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
        logger.debug(f"FileBackend: stored entry {entry.id}")
        return entry.id

    async def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        query_lower = query.lower()
        query_terms = query_lower.split()

        scored: list[tuple[float, MemoryEntry]] = []
        for entry in await self.list_all():
            content_lower = entry.content.lower()
            # Score: number of query terms found in content
            score = sum(1 for term in query_terms if term in content_lower)
            if score > 0:
                scored.append((score, entry))

        # Sort by score descending, then by recency
        scored.sort(key=lambda x: (x[0], x[1].created_at), reverse=True)
        return [entry for _, entry in scored[:top_k]]

    async def delete(self, entry_id: str) -> bool:
        path = self._entry_path(entry_id)
        if path.exists():
            path.unlink()
            logger.debug(f"FileBackend: deleted entry {entry_id}")
            return True
        return False

    async def list_all(self) -> list[MemoryEntry]:
        entries: list[MemoryEntry] = []

        for path in sorted(self._dir.glob("*.md"), reverse=True):
            try:
                entry = self._parse_file(path)
                if entry:
                    entries.append(entry)
            except Exception as e:
                logger.warning(f"FileBackend: failed to parse {path.name}: {e}")

        return entries

    def _parse_file(self, path: Path) -> MemoryEntry | None:
        """Parse a .md memory file back into a MemoryEntry."""
        from datetime import datetime

        text = path.read_text(encoding="utf-8")
        lines = text.split("\n")

        entry_id = path.stem
        created_at = datetime.now()
        source = ""
        tags: list[str] = []
        content_lines: list[str] = []
        in_header = True

        for line in lines:
            if in_header and line.startswith("<!-- ") and line.endswith(" -->"):
                inner = line[5:-4].strip()
                if inner.startswith("id:"):
                    entry_id = inner[3:].strip()
                elif inner.startswith("created_at:"):
                    try:
                        created_at = datetime.fromisoformat(inner[11:].strip())
                    except ValueError:
                        pass
                elif inner.startswith("source:"):
                    source = inner[7:].strip()
                elif inner.startswith("tags:"):
                    tag_str = inner[5:].strip()
                    tags = [t.strip() for t in tag_str.split(",") if t.strip()]
            else:
                in_header = False
                content_lines.append(line)

        content = "\n".join(content_lines).strip()
        if not content:
            return None

        return MemoryEntry(
            id=entry_id,
            content=content,
            tags=tags,
            created_at=created_at,
            source=source,
        )
