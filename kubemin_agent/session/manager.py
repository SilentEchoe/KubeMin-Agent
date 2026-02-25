"""Session manager for conversation persistence."""

import json
from pathlib import Path
from typing import Any

from loguru import logger


class SessionManager:
    """
    Manages conversation sessions with JSONL persistence.

    Each session is stored as a JSONL file keyed by channel:chat_id.
    """

    MAX_HISTORY = 50

    def __init__(self, workspace: Path) -> None:
        self.sessions_dir = workspace.parent / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, list[dict[str, Any]]] = {}

    def _session_path(self, session_key: str) -> Path:
        """Get the file path for a session."""
        safe_key = session_key.replace(":", "_").replace("/", "_")
        return self.sessions_dir / f"{safe_key}.jsonl"

    def get_history(self, session_key: str) -> list[dict[str, Any]]:
        """
        Get conversation history for a session.

        Args:
            session_key: Session identifier (format: channel:chat_id).

        Returns:
            List of message dicts.
        """
        if session_key in self._cache:
            return self._cache[session_key][-self.MAX_HISTORY :]

        path = self._session_path(session_key)
        if not path.exists():
            self._cache[session_key] = []
            return []

        messages: list[dict[str, Any]] = []
        try:
            for line in path.read_text(encoding="utf-8").strip().split("\n"):
                if line:
                    messages.append(json.loads(line))
        except Exception as e:
            logger.warning(f"Failed to load session {session_key}: {e}")
            messages = []

        self._cache[session_key] = messages
        return messages[-self.MAX_HISTORY :]

    def save_turn(self, session_key: str, user_message: str, assistant_response: str) -> None:
        """
        Save a conversation turn (user + assistant) to the session.

        Args:
            session_key: Session identifier.
            user_message: The user's message.
            assistant_response: The assistant's response.
        """
        if session_key not in self._cache:
            self._cache[session_key] = []

        user_msg = {"role": "user", "content": user_message}
        assistant_msg = {"role": "assistant", "content": assistant_response}

        self._cache[session_key].append(user_msg)
        self._cache[session_key].append(assistant_msg)

        # Append to file
        path = self._session_path(session_key)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(user_msg, ensure_ascii=False) + "\n")
            f.write(json.dumps(assistant_msg, ensure_ascii=False) + "\n")

    def clear(self, session_key: str) -> None:
        """Clear a session's history."""
        self._cache.pop(session_key, None)
        path = self._session_path(session_key)
        if path.exists():
            path.unlink()
        logger.debug(f"Session cleared: {session_key}")
