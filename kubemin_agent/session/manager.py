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
            f"# Active Execution Plan",
            f"\n## Objective",
            f"{original_message}",
            f"\n## Tasks",
        ]
        
        for t in tasks:
            task_id = getattr(t, 'task_id', t.get('task_id') if isinstance(t, dict) else 'unknown')
            agent = getattr(t, 'agent_name', t.get('agent_name') if isinstance(t, dict) else 'unknown')
            desc = getattr(t, 'description', t.get('description') if isinstance(t, dict) else 'unknown')
            lines.append(f"- [ ] **{task_id}** ({agent}): {desc}")
            
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def update_active_plan_task_status(self, session_key: str, task_id: str, status: str, result_summary: str = "") -> None:
        """Update a task's status in the active plan document. Status: '[-]' or '[x]'."""
        path = self._active_plan_doc_path(session_key)
        if not path.exists():
            return
            
        content = path.read_text(encoding="utf-8")
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
                
        path.write_text("\n".join(lines), encoding="utf-8")

    def get_active_plan_doc_path(self, session_key: str) -> Path | None:
        """Get the path to the active plan doc if it exists."""
        path = self._active_plan_doc_path(session_key)
        return path if path.exists() else None
