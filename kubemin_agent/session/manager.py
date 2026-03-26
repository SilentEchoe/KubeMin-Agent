"""Session manager for conversation persistence."""

import json
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from loguru import logger


class SessionManager:
    """
    Manages conversation sessions with JSONL persistence.

    Each session is stored as a JSONL file keyed by channel:chat_id.
    """

    MAX_HISTORY = 50

    def __init__(
        self,
        workspace: Path,
        max_history: int = 50,
        cache_message_limit: int = 200,
        cache_session_limit: int = 200,
        file_max_mb: int = 50,
        retention_days: int = 30,
    ) -> None:
        self.sessions_dir = workspace.parent / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._cache: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        self._max_history = max(1, max_history)
        self._cache_message_limit = max(2, cache_message_limit)
        self._cache_session_limit = max(1, cache_session_limit)
        self._session_file_max_bytes = max(1, file_max_mb) * 1024 * 1024
        self._retention_days = max(1, retention_days)
        self._cleanup_old_session_files()

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
            self._cache.move_to_end(session_key)
            return self._cache[session_key][-self._max_history :]

        messages = self._load_messages_from_disk(session_key)
        self._cache_session(session_key, messages)
        return self._cache[session_key][-self._max_history :]

    def get_history_page(
        self,
        session_key: str,
        page: int = 1,
        page_size: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Get paginated conversation history for a session.

        Args:
            session_key: Session identifier (format: channel:chat_id).
            page: 1-based page index from newest to oldest.
            page_size: Number of messages per page.

        Returns:
            A page of messages in chronological order.
        """
        if page <= 0 or page_size <= 0:
            return []

        messages = self._load_messages_from_disk(session_key)
        if not messages and session_key in self._cache:
            messages = list(self._cache[session_key])
        if not messages:
            return []

        end = len(messages) - (page - 1) * page_size
        if end <= 0:
            return []
        start = max(0, end - page_size)
        return messages[start:end]

    def save_turn(self, session_key: str, user_message: str, assistant_response: str) -> None:
        """
        Save a conversation turn (user + assistant) to the session.

        Args:
            session_key: Session identifier.
            user_message: The user's message.
            assistant_response: The assistant's response.
        """
        cached_messages = (
            list(self._cache[session_key])
            if session_key in self._cache
            else self._load_messages_from_disk(session_key)
        )

        user_msg = {"role": "user", "content": user_message}
        assistant_msg = {"role": "assistant", "content": assistant_response}

        cached_messages.append(user_msg)
        cached_messages.append(assistant_msg)
        self._cache_session(session_key, cached_messages)

        # Append to file
        path = self._session_path(session_key)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(user_msg, ensure_ascii=False) + "\n")
            f.write(json.dumps(assistant_msg, ensure_ascii=False) + "\n")
        self._truncate_session_file(path)

    def clear(self, session_key: str) -> None:
        """Clear a session's history."""
        self._cache.pop(session_key, None)
        path = self._session_path(session_key)
        if path.exists():
            path.unlink()
        logger.debug(f"Session cleared: {session_key}")

    def _plan_path(self, session_key: str) -> Path:
        """Get the file path for a session's pending plan."""
        safe_key = session_key.replace(":", "_").replace("/", "_")
        return self.sessions_dir / f"{safe_key}.plan.json"

    def save_plan(self, session_key: str, plan_data: dict[str, Any]) -> None:
        """Save a pending execution plan."""
        path = self._plan_path(session_key)
        path.write_text(json.dumps(plan_data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug(f"Plan saved: {session_key}")

    def get_plan(self, session_key: str) -> dict[str, Any] | None:
        """Retrieve a pending execution plan if it exists."""
        path = self._plan_path(session_key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to load plan {session_key}: {e}")
            return None

    def clear_plan(self, session_key: str) -> None:
        """Clear a session's pending plan."""
        path = self._plan_path(session_key)
        if path.exists():
            path.unlink()
            logger.debug(f"Plan cleared: {session_key}")

    def _active_plan_doc_path(self, session_key: str) -> Path:
        """Get the file path for a session's active execution plan document."""
        safe_key = session_key.replace(":", "_").replace("/", "_")
        return self.sessions_dir / f"{safe_key}.active_plan.md"

    def init_active_plan_doc(self, session_key: str, original_message: str, tasks: list[Any]) -> Path:
        """Initialize the active plan markdown document."""
        path = self._active_plan_doc_path(session_key)

        lines = [
            "# Active Execution Plan",
            "\n## Objective",
            f"{original_message}",
            "\n## Tasks",
        ]

        for t in tasks:
            task_id = getattr(t, 'task_id', t.get('task_id') if isinstance(t, dict) else 'unknown')
            agent = getattr(t, 'agent_name', t.get('agent_name') if isinstance(t, dict) else 'unknown')
            desc = getattr(t, 'description', t.get('description') if isinstance(t, dict) else 'unknown')
            lines.append(f"- [ ] **{task_id}** ({agent}): {desc}")

        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def update_active_plan_task_status(
        self,
        session_key: str,
        task_id: str,
        status: str,
        result_summary: str = "",
        existing_content: str | None = None,
    ) -> str:
        """Update a task's status in the active plan document. Status: '[-]' or '[x]'."""
        path = self._active_plan_doc_path(session_key)
        if not path.exists():
            return existing_content or ""

        content = existing_content if existing_content is not None else path.read_text(encoding="utf-8")
        lines = content.splitlines()

        for i, line in enumerate(lines):
            if line.startswith("- [") and f"**{task_id}**" in line:
                # Replace the checkbox marker (e.g. "- [ ]" or "- [-]") with the new status
                new_line = line[:2] + status + line[5:]
                if status == "[x]" and result_summary:
                    # Append a concise summary snippet
                    snippet = result_summary.replace("\n", " ")[:100]
                    if len(result_summary) > 100:
                        snippet += "..."
                    new_line += f" -> *Result: {snippet}*"
                lines[i] = new_line
                break

        updated_content = "\n".join(lines)
        path.write_text(updated_content, encoding="utf-8")
        return updated_content

    def get_active_plan_doc_path(self, session_key: str) -> Path | None:
        """Get the path to the active plan doc if it exists."""
        path = self._active_plan_doc_path(session_key)
        return path if path.exists() else None

    def _truncate_session_file(self, path: Path) -> None:
        """Truncate oversized session files while preserving recent messages."""
        try:
            if not path.exists() or path.stat().st_size <= self._session_file_max_bytes:
                return
            lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
            min_keep_lines = min(len(lines), 2)
            selected_reversed: list[str] = []
            selected_bytes = 0
            for line in reversed(lines):
                line_bytes = len(line.encode("utf-8")) + 1
                over_limit = selected_bytes + line_bytes > self._session_file_max_bytes
                if over_limit and len(selected_reversed) >= min_keep_lines:
                    break
                selected_reversed.append(line)
                selected_bytes += line_bytes
            trimmed = list(reversed(selected_reversed))
            content = "\n".join(trimmed)
            if content:
                content += "\n"
            path.write_text(content, encoding="utf-8")
            logger.info(
                "Session file truncated: "
                f"{path.name}, lines={len(trimmed)}, bytes={len(content.encode('utf-8'))}"
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to truncate session file {path}: {e}")

    def _load_messages_from_disk(self, session_key: str) -> list[dict[str, Any]]:
        """Load all messages for a session from disk."""
        path = self._session_path(session_key)
        if not path.exists():
            return []

        messages: list[dict[str, Any]] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    messages.append(json.loads(line))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to load session {session_key}: {e}")
            return []
        return messages

    def _cache_session(self, session_key: str, messages: list[dict[str, Any]]) -> None:
        """Update in-memory cache with LRU eviction on session count."""
        self._cache[session_key] = messages[-self._cache_message_limit :]
        self._cache.move_to_end(session_key)
        while len(self._cache) > self._cache_session_limit:
            evicted_session_key, _ = self._cache.popitem(last=False)
            logger.debug(f"Session cache evicted: {evicted_session_key}")

    def _cleanup_old_session_files(self) -> None:
        """Cleanup expired session artifacts according to retention policy."""
        cutoff = datetime.now() - timedelta(days=self._retention_days)
        for path in self.sessions_dir.glob("*"):
            if not path.is_file():
                continue
            try:
                modified_at = datetime.fromtimestamp(path.stat().st_mtime)
                if modified_at < cutoff:
                    path.unlink()
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Failed to cleanup expired session file {path}: {e}")
