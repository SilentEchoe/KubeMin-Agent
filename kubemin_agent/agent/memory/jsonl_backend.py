"""JSONL-based memory backend with TF-IDF search."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

from loguru import logger

from kubemin_agent.agent.memory.backend import MemoryBackend
from kubemin_agent.agent.memory.entry import MemoryEntry


class JSONLBackend(MemoryBackend):
    """
    Memory backend that stores entries in a single .jsonl file.

    Search is implemented via TF-IDF scoring for better relevance
    ranking compared to simple keyword matching.
    Suitable for medium-scale usage without external dependencies.
    """

    def __init__(self, memory_dir: Path) -> None:
        self._dir = memory_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "memories.jsonl"

    async def store(self, entry: MemoryEntry) -> str:
        with open(self._file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        logger.debug(f"JSONLBackend: stored entry {entry.id}")
        return entry.id

    async def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        entries = await self.list_all()
        if not entries:
            return []

        query_terms = self._tokenize(query)
        if not query_terms:
            return entries[:top_k]

        # Build document frequency
        doc_freq: Counter[str] = Counter()
        doc_tokens: list[list[str]] = []
        for entry in entries:
            tokens = self._tokenize(entry.content)
            doc_tokens.append(tokens)
            for term in set(tokens):
                doc_freq[term] += 1

        n_docs = len(entries)

        # Score each entry
        scored: list[tuple[float, MemoryEntry]] = []
        for entry, tokens in zip(entries, doc_tokens):
            score = self._tfidf_score(query_terms, tokens, doc_freq, n_docs)
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:top_k]]

    async def delete(self, entry_id: str) -> bool:
        entries = await self.list_all()
        original_count = len(entries)
        entries = [e for e in entries if e.id != entry_id]

        if len(entries) == original_count:
            return False

        self._rewrite(entries)
        logger.debug(f"JSONLBackend: deleted entry {entry_id}")
        return True

    async def list_all(self) -> list[MemoryEntry]:
        if not self._file.exists():
            return []

        entries: list[MemoryEntry] = []
        for line in self._file.read_text(encoding="utf-8").strip().splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                entries.append(MemoryEntry.from_dict(data))
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"JSONLBackend: skipping malformed line: {e}")

        # Newest first
        entries.sort(key=lambda e: e.created_at, reverse=True)
        return entries

    def _rewrite(self, entries: list[MemoryEntry]) -> None:
        """Rewrite the entire JSONL file (used after delete)."""
        with open(self._file, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple whitespace + punctuation tokenizer."""
        import re
        return re.findall(r"\w+", text.lower())

    @staticmethod
    def _tfidf_score(
        query_terms: list[str],
        doc_terms: list[str],
        doc_freq: Counter[str],
        n_docs: int,
    ) -> float:
        """Compute TF-IDF similarity score between query and document."""
        if not doc_terms:
            return 0.0

        doc_counter = Counter(doc_terms)
        doc_len = len(doc_terms)
        score = 0.0

        for term in query_terms:
            tf = doc_counter.get(term, 0) / doc_len
            df = doc_freq.get(term, 0)
            if df > 0:
                idf = math.log(n_docs / df)
                score += tf * idf

        return score
