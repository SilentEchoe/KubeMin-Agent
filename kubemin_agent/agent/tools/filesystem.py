"""Filesystem tools for reading and writing files within workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from kubemin_agent.agent.tools.base import Tool

# Files that should never be read or written
_SENSITIVE_PATTERNS = {
    ".env",
    ".env.local",
    ".env.production",
    "id_rsa",
    "id_ed25519",
    ".pem",
    ".key",
    "credentials",
    "secrets.yaml",
    "secrets.yml",
}

MAX_READ_LENGTH = 4000


class ReadFileTool(Tool):
    """Read a file's contents within the workspace."""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace.resolve()

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read the contents of a file. The path must be within the workspace directory. "
            "Sensitive files (.env, private keys, credentials) are not accessible."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative or absolute path to the file to read.",
                },
            },
            "required": ["path"],
        }

    async def execute(self, *, path: str) -> str:
        resolved = self._resolve_path(path)
        if isinstance(resolved, str):
            return resolved  # error message

        if not resolved.exists():
            return f"Error: file not found: {path}"
        if not resolved.is_file():
            return f"Error: not a file: {path}"

        try:
            content = resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return f"Error: cannot read binary file: {path}"
        except Exception as e:
            return f"Error reading file: {e}"

        if len(content) > MAX_READ_LENGTH:
            return (
                content[:MAX_READ_LENGTH]
                + f"\n\n... (truncated, total {len(content)} characters)"
            )
        return content

    def _resolve_path(self, path: str) -> Path | str:
        """Resolve path and validate it is within workspace and not sensitive."""
        try:
            p = Path(path)
            if not p.is_absolute():
                p = self._workspace / p
            p = p.resolve()
        except Exception as e:
            return f"Error: invalid path: {e}"

        if not str(p).startswith(str(self._workspace)):
            return f"Error: path is outside workspace: {path}"

        for pattern in _SENSITIVE_PATTERNS:
            if p.name == pattern or p.name.endswith(pattern):
                return f"Error: access denied to sensitive file: {p.name}"

        return p


class WriteFileTool(Tool):
    """Write content to a file within the workspace."""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace.resolve()

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "Write content to a file. Creates the file if it doesn't exist, "
            "overwrites if it does. Parent directories are created automatically. "
            "The path must be within the workspace directory."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative or absolute path to the file to write.",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file.",
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, *, path: str, content: str) -> str:
        try:
            p = Path(path)
            if not p.is_absolute():
                p = self._workspace / p
            p = p.resolve()
        except Exception as e:
            return f"Error: invalid path: {e}"

        if not str(p).startswith(str(self._workspace)):
            return f"Error: path is outside workspace: {path}"

        for pattern in _SENSITIVE_PATTERNS:
            if p.name == pattern or p.name.endswith(pattern):
                return f"Error: cannot write to sensitive file: {p.name}"

        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            logger.debug(f"WriteFileTool: wrote {len(content)} chars to {p}")
            return f"Successfully wrote {len(content)} characters to {path}"
        except Exception as e:
            return f"Error writing file: {e}"
