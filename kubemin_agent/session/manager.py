"""JSONL session persistence with optional memory indexing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kubemin_agent.agent.memory.manager import MemoryManager
from kubemin_agent.agent.memory.scope import MemoryScope
from kubemin_agent.utils.helpers import sanitize_session_key


class SessionManager:
    """Persist conversation turns and optionally sync them into memory search."""

    def __init__(self, root: Path, memory_manager: MemoryManager | None = None) -> None:
        self.root = root.expanduser()
        self.sessions_dir = self.root / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.memory_manager = memory_manager

    def session_path(self, session_key: str) -> Path:
        """Return JSONL path for a session."""
        return self.sessions_dir / f"{sanitize_session_key(session_key)}.jsonl"

    def save_turn(
        self,
        session_key: str,
        user_message: str,
        assistant_response: str,
        *,
        scope: MemoryScope | None = None,
        request_id: str = "",
    ) -> None:
        """Append one turn and sync to session search when scoped memory is available."""
        path = self.session_path(session_key)
        records = [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_response},
        ]
        with path.open("a", encoding="utf-8") as file:
            for record in records:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")

        if self.memory_manager and scope:
            self.memory_manager.sync_turn(
                scope=scope,
                session_key=session_key,
                user_message=user_message,
                assistant_response=assistant_response,
                request_id=request_id,
            )

    def get_history(self, session_key: str) -> list[dict[str, Any]]:
        """Load a session history from JSONL."""
        path = self.session_path(session_key)
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows
