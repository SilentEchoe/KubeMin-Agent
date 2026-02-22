"""Tool interfaces, registry, and built-in tools for the chat agent."""

from __future__ import annotations

import asyncio
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class Tool(ABC):
    """Base tool contract."""

    _TYPE_MAP = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        pass

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        pass

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        schema = self.parameters or {}
        if schema.get("type", "object") != "object":
            raise ValueError(f"Schema must be object type, got {schema.get('type')!r}")
        return self._validate(params, {**schema, "type": "object"}, "")

    def _validate(self, value: Any, schema: dict[str, Any], path: str) -> list[str]:
        expected_type = schema.get("type")
        label = path or "parameter"
        if expected_type in self._TYPE_MAP and not isinstance(value, self._TYPE_MAP[expected_type]):
            return [f"{label} should be {expected_type}"]

        errors: list[str] = []
        if "enum" in schema and value not in schema["enum"]:
            errors.append(f"{label} must be one of {schema['enum']}")
        if expected_type in ("integer", "number"):
            if "minimum" in schema and value < schema["minimum"]:
                errors.append(f"{label} must be >= {schema['minimum']}")
            if "maximum" in schema and value > schema["maximum"]:
                errors.append(f"{label} must be <= {schema['maximum']}")
        if expected_type == "string":
            if "minLength" in schema and len(value) < schema["minLength"]:
                errors.append(f"{label} must be at least {schema['minLength']} chars")
            if "maxLength" in schema and len(value) > schema["maxLength"]:
                errors.append(f"{label} must be at most {schema['maxLength']} chars")
        if expected_type == "object":
            properties = schema.get("properties", {})
            for key in schema.get("required", []):
                if key not in value:
                    errors.append(f"missing required {path + '.' + key if path else key}")
            for key, item in value.items():
                if key in properties:
                    next_path = f"{path}.{key}" if path else key
                    errors.extend(self._validate(item, properties[key], next_path))
        if expected_type == "array" and "items" in schema:
            for idx, item in enumerate(value):
                next_path = f"{path}[{idx}]" if path else f"[{idx}]"
                errors.extend(self._validate(item, schema["items"], next_path))
        return errors

    def to_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """In-memory tool registry."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def get_definitions(self) -> list[dict[str, Any]]:
        return [tool.to_schema() for tool in self._tools.values()]

    async def execute(self, name: str, params: dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if not tool:
            return f"Error: Tool '{name}' not found"
        try:
            errors = tool.validate_params(params)
            if errors:
                return f"Error: Invalid parameters for tool '{name}': " + "; ".join(errors)
            return await tool.execute(**params)
        except Exception as exc:  # pragma: no cover - runtime safeguard
            return f"Error executing {name}: {exc}"


def _safe_resolve_path(path: str, workspace: Path, restrict_to_workspace: bool) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = workspace / candidate
    resolved = candidate.resolve()
    if restrict_to_workspace:
        workspace_root = workspace.resolve()
        if resolved != workspace_root and workspace_root not in resolved.parents:
            raise PermissionError(f"Path outside workspace: {resolved}")
    return resolved


class ReadFileTool(Tool):
    def __init__(self, workspace: Path, restrict_to_workspace: bool = True):
        self.workspace = workspace
        self.restrict_to_workspace = restrict_to_workspace

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read text content from a file."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to file"},
            },
            "required": ["path"],
        }

    async def execute(self, path: str, **kwargs: Any) -> str:
        file_path = _safe_resolve_path(path, self.workspace, self.restrict_to_workspace)
        if not file_path.exists():
            return f"Error: File not found: {path}"
        if not file_path.is_file():
            return f"Error: Not a file: {path}"
        content = file_path.read_text(encoding="utf-8")
        max_chars = 20000
        if len(content) > max_chars:
            return content[:max_chars] + f"\n... (truncated {len(content) - max_chars} chars)"
        return content


class WriteFileTool(Tool):
    def __init__(self, workspace: Path, restrict_to_workspace: bool = True):
        self.workspace = workspace
        self.restrict_to_workspace = restrict_to_workspace

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "Write text content to a file. Creates directories if needed."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to file"},
                "content": {"type": "string", "description": "File content"},
            },
            "required": ["path", "content"],
        }

    async def execute(self, path: str, content: str, **kwargs: Any) -> str:
        file_path = _safe_resolve_path(path, self.workspace, self.restrict_to_workspace)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {file_path}"


class ListDirTool(Tool):
    def __init__(self, workspace: Path, restrict_to_workspace: bool = True):
        self.workspace = workspace
        self.restrict_to_workspace = restrict_to_workspace

    @property
    def name(self) -> str:
        return "list_dir"

    @property
    def description(self) -> str:
        return "List files and directories."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to directory"},
            },
            "required": ["path"],
        }

    async def execute(self, path: str, **kwargs: Any) -> str:
        dir_path = _safe_resolve_path(path, self.workspace, self.restrict_to_workspace)
        if not dir_path.exists():
            return f"Error: Directory not found: {path}"
        if not dir_path.is_dir():
            return f"Error: Not a directory: {path}"
        items = []
        for item in sorted(dir_path.iterdir()):
            suffix = "/" if item.is_dir() else ""
            items.append(f"{item.name}{suffix}")
        return "\n".join(items) if items else "(empty directory)"


class ExecTool(Tool):
    def __init__(self, workspace: Path, timeout_s: int = 30, restrict_to_workspace: bool = True):
        self.workspace = workspace
        self.timeout_s = timeout_s
        self.restrict_to_workspace = restrict_to_workspace
        self._deny_patterns = [
            r"\brm\s+-[rf]{1,2}\b",
            r"\bdel\s+/[fq]\b",
            r"\brmdir\s+/s\b",
            r"\b(format|mkfs|diskpart)\b",
            r"\bdd\s+if=",
            r">\s*/dev/sd",
            r"\b(shutdown|reboot|poweroff)\b",
            r":\(\)\s*\{.*\};\s*:",
        ]

    @property
    def name(self) -> str:
        return "exec"

    @property
    def description(self) -> str:
        return "Execute a shell command in the workspace."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"},
                "working_dir": {
                    "type": "string",
                    "description": "Optional working directory. Relative paths are under workspace.",
                },
            },
            "required": ["command"],
        }

    async def execute(self, command: str, working_dir: str | None = None, **kwargs: Any) -> str:
        lowered = command.lower()
        for pattern in self._deny_patterns:
            if re.search(pattern, lowered):
                return "Error: Command blocked by safety guard"

        if working_dir:
            cwd = _safe_resolve_path(working_dir, self.workspace, self.restrict_to_workspace)
        else:
            cwd = self.workspace.resolve()

        if self.restrict_to_workspace and cwd != self.workspace.resolve() and self.workspace.resolve() not in cwd.parents:
            return "Error: working_dir is outside workspace"

        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout_s)
        except asyncio.TimeoutError:
            process.kill()
            return f"Error: command timed out after {self.timeout_s}s"

        output_parts = []
        if stdout:
            output_parts.append(stdout.decode("utf-8", errors="replace"))
        if stderr:
            err = stderr.decode("utf-8", errors="replace")
            if err.strip():
                output_parts.append(f"STDERR:\n{err}")
        if process.returncode != 0:
            output_parts.append(f"\nExit code: {process.returncode}")

        result = "\n".join(output_parts) if output_parts else "(no output)"
        max_chars = 10000
        if len(result) > max_chars:
            result = result[:max_chars] + f"\n... (truncated {len(result) - max_chars} chars)"
        return result

