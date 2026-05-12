"""Common helper functions."""

from __future__ import annotations

import re


def truncate_output(text: str, max_length: int = 4000) -> str:
    """Trim long text while preserving both head and tail."""
    if len(text) <= max_length:
        return text
    half = max_length // 2
    return text[:half] + f"\n\n... [truncated {len(text) - max_length} chars] ...\n\n" + text[-half:]


def sanitize_identifier(value: str, default: str = "default") -> str:
    """Return a filesystem-safe tenant/user/agent identifier."""
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]", "_", (value or "").strip())
    cleaned = cleaned.strip("._-")
    return cleaned or default


def sanitize_session_key(key: str) -> str:
    """Return a filesystem-safe session key."""
    return sanitize_identifier(key, default="session")
