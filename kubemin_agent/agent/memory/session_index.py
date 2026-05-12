"""SQLite FTS5-backed session search."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from kubemin_agent.agent.memory.scope import MemoryScope


@dataclass(frozen=True)
class SessionSearchResult:
    """One scoped session search hit."""

    session_key: str
    request_id: str
    agent_name: str
    created_at: str
    snippet: str


class SessionSearchIndex:
    """Large-capacity session recall using SQLite FTS5."""

    def __init__(self, root: Path, enabled: bool = True) -> None:
        self.root = root.expanduser()
        self.enabled = enabled
        self.db_path = self.root / "memory" / "session_search.sqlite3"
        if self.enabled:
            self.root.mkdir(parents=True, exist_ok=True)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()

    def index_turn(
        self,
        scope: MemoryScope,
        session_key: str,
        user_message: str,
        assistant_response: str,
        request_id: str = "",
    ) -> None:
        """Index one completed conversation turn."""
        if not self.enabled:
            return
        content = f"User: {user_message}\nAssistant: {assistant_response}"
        created_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO session_turns (
                    tenant_id, user_id, agent_name, session_key, request_id,
                    created_at, user_message, assistant_response
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scope.tenant_id,
                    scope.user_id,
                    scope.agent_name,
                    session_key,
                    request_id,
                    created_at,
                    user_message,
                    assistant_response,
                ),
            )
            rowid = cur.lastrowid
            conn.execute("INSERT INTO session_fts(rowid, content) VALUES (?, ?)", (rowid, content))

    def search(
        self,
        scope: MemoryScope,
        query: str,
        top_k: int = 5,
        agent_name: str | None = None,
        session_key: str | None = None,
        request_id: str | None = None,
    ) -> list[SessionSearchResult]:
        """Search prior turns for this tenant and user."""
        if not self.enabled or not query.strip() or top_k <= 0:
            return []

        match_query = self._to_match_query(query)
        if not match_query:
            return []

        where = ["t.tenant_id = ?", "t.user_id = ?"]
        params: list[str | int] = [scope.tenant_id, scope.user_id]
        if agent_name:
            where.append("t.agent_name = ?")
            params.append(agent_name)
        if session_key:
            where.append("t.session_key = ?")
            params.append(session_key)
        if request_id:
            where.append("t.request_id = ?")
            params.append(request_id)

        params.extend([match_query, top_k])
        sql = f"""
            SELECT
                t.session_key,
                t.request_id,
                t.agent_name,
                t.created_at,
                snippet(session_fts, 0, '[', ']', '...', 12) AS snippet
            FROM session_fts
            JOIN session_turns t ON t.id = session_fts.rowid
            WHERE {' AND '.join(where)}
              AND session_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """

        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            SessionSearchResult(
                session_key=row[0],
                request_id=row[1],
                agent_name=row[2],
                created_at=row[3],
                snippet=row[4],
            )
            for row in rows
        ]

    def _initialize(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS fts_probe USING fts5(content)")
                conn.execute("DROP TABLE IF EXISTS fts_probe")
            except sqlite3.OperationalError as exc:
                raise RuntimeError("SQLite FTS5 is required for session_search") from exc
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS session_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    session_key TEXT NOT NULL,
                    request_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    user_message TEXT NOT NULL,
                    assistant_response TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_session_turns_scope
                  ON session_turns(tenant_id, user_id, agent_name, session_key, request_id);
                CREATE VIRTUAL TABLE IF NOT EXISTS session_fts USING fts5(content);
                """
            )

    @staticmethod
    def _to_match_query(query: str) -> str:
        tokens = re.findall(r"[\w\u4e00-\u9fff]+", query.lower())
        tokens = [token for token in tokens if token]
        return " OR ".join(tokens[:12])
