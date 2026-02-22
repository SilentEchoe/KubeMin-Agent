"""Simple JSONL-backed chat session storage."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


def _safe_filename(name: str) -> str:
    unsafe = '<>:"/\\|?*'
    for ch in unsafe:
        name = name.replace(ch, "_")
    return name.strip()


@dataclass
class Session:
    key: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def add_message(self, role: str, content: str) -> None:
        self.messages.append(
            {
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
        self.updated_at = datetime.utcnow()

    def get_history(self, max_messages: int = 30) -> list[dict[str, str]]:
        recent = self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages
        return [{"role": m["role"], "content": m["content"]} for m in recent]


class SessionManager:
    """Persistent session manager."""

    def __init__(self, sessions_dir: Path):
        self.sessions_dir = sessions_dir.expanduser()
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Session] = {}

    def _path(self, key: str) -> Path:
        return self.sessions_dir / f"{_safe_filename(key.replace(':', '_'))}.jsonl"

    def get_or_create(self, key: str) -> Session:
        if key in self._cache:
            return self._cache[key]
        session = self._load(key)
        if session is None:
            session = Session(key=key)
        self._cache[key] = session
        return session

    def save(self, session: Session) -> None:
        path = self._path(session.key)
        with open(path, "w", encoding="utf-8") as fp:
            metadata = {
                "_type": "metadata",
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
            }
            fp.write(json.dumps(metadata) + "\n")
            for msg in session.messages:
                fp.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self._cache[session.key] = session

    def _load(self, key: str) -> Session | None:
        path = self._path(key)
        if not path.exists():
            return None
        messages: list[dict[str, Any]] = []
        created_at = datetime.utcnow()
        updated_at = created_at
        with open(path, encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry.get("_type") == "metadata":
                    if entry.get("created_at"):
                        created_at = datetime.fromisoformat(entry["created_at"])
                    if entry.get("updated_at"):
                        updated_at = datetime.fromisoformat(entry["updated_at"])
                else:
                    messages.append(entry)
        return Session(key=key, messages=messages, created_at=created_at, updated_at=updated_at)

