"""Shell command execution tool with safety constraints."""

from __future__ import annotations

import asyncio
import re
import shlex
from pathlib import Path
from typing import Any

from kubemin_agent.agent.tools.base import Tool
from kubemin_agent.agent.tools.sandbox import (
    SandboxMode,
    SandboxPolicy,
    SandboxRunner,
    SandboxRuntime,
    SandboxUnavailableError,
)

# Whitelisted command prefixes
_ALLOWED_COMMANDS = {
    "ls", "cat", "echo", "grep", "find", "wc", "head", "tail",
    "pwd", "env", "date", "curl", "wget",
    "git", "python3", "python", "pip", "node", "npm", "npx",
    "kubectl", "helm",
    "sort", "uniq", "diff", "tr", "cut", "awk", "sed",
    "du", "df", "file", "which", "whoami", "uname",
    "tar", "zip", "unzip", "gzip", "gunzip",
    "jq", "yq",
    "make", "go", "cargo", "rustc",
    "ruff", "mypy", "pytest", "black", "isort",
}

# Patterns that are always blocked
_BLOCKED_PATTERNS = [
    r"\brm\s+-rf\b",
    r"\brm\s+-fr\b",
    r"\bsudo\b",
    r"\bchmod\b",
    r"\bchown\b",
    r"\bmkfs\b",
    r"\bdd\b\s+if=",
    r"\bkill\b",
    r"\bkillall\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\b>\s*/dev/",
    r"\|\s*(sh|bash|zsh|dash)\b",
    r";\s*(sh|bash|zsh|dash)\b",
    r"\beval\b",
    r"\bexec\b",
    r"\bnohup\b.*&",
]

MAX_OUTPUT_LENGTH = 4000
DEFAULT_TIMEOUT = 30


class ShellTool(Tool):
    """Execute shell commands with safety constraints."""

    def __init__(
        self,
        workspace: Path | None = None,
        default_timeout: int = DEFAULT_TIMEOUT,
        restrict_to_workspace: bool = False,
        strict_path_guard: bool = True,
        sandbox_mode: str = "off",
        sandbox_runtime: str = "auto",
        sandbox_allow_network: bool = False,
    ) -> None:
        self._workspace = workspace.resolve() if workspace else None
        self._default_timeout = min(max(default_timeout, 1), 120)
        self._strict_path_guard = strict_path_guard and self._workspace is not None
        self._restrict_to_workspace = (
            restrict_to_workspace or self._strict_path_guard
        ) and self._workspace is not None
        self._sandbox_mode = self._normalize_mode(sandbox_mode)
        self._sandbox_runtime = self._normalize_runtime(sandbox_runtime)
        self._sandbox_runner = SandboxRunner(
            workspace=self._workspace or Path.cwd(),
            policy=SandboxPolicy(
                mode=self._sandbox_mode,
                runtime=self._sandbox_runtime,
                allow_network=sandbox_allow_network,
            ),
        )

    @property
    def name(self) -> str:
        return "run_command"

    @property
    def description(self) -> str:
        return (
            "Execute a shell command and return stdout + stderr. "
            "Only safe, read-oriented commands are allowed. "
            "Destructive operations (rm -rf, sudo, chmod, etc.) are blocked."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
                "timeout": {
                    "type": "integer",
                    "description": (
                        "Timeout in seconds (defaults to tool config, max 120)."
                    ),
                },
            },
            "required": ["command"],
        }

    async def execute(self, **kwargs: Any) -> str:
        command = kwargs.get("command")
        if not isinstance(command, str):
            return "Error: command must be a string"
        timeout_raw = kwargs.get("timeout")
        timeout: int | None
        if timeout_raw is None:
            timeout = None
        elif isinstance(timeout_raw, int):
            timeout = timeout_raw
        else:
            return "Error: timeout must be an integer"

        timeout = self._default_timeout if timeout is None else min(max(timeout, 1), 120)

        # Safety checks
        safety_error = self._check_safety(command)
        if safety_error:
            return safety_error

        try:
            wrapped_cmd = self._sandbox_runner.build_command(command)
            if wrapped_cmd:
                proc = await asyncio.create_subprocess_exec(
                    *wrapped_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                proc = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(self._workspace) if self._restrict_to_workspace else None,
                )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except SandboxUnavailableError as e:
            return f"Error: {e}"
        except asyncio.TimeoutError:
            proc.kill()
            return f"Error: command timed out after {timeout}s"
        except Exception as e:
            return f"Error executing command: {e}"

        result_parts: list[str] = []

        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()

        if stdout_text:
            result_parts.append(stdout_text)
        if stderr_text:
            result_parts.append(f"[stderr]\n{stderr_text}")

        result_parts.append(f"[exit_code: {proc.returncode}]")

        result = "\n".join(result_parts)
        if len(result) > MAX_OUTPUT_LENGTH:
            result = result[:MAX_OUTPUT_LENGTH] + f"\n... (truncated, total {len(result)} chars)"

        return result

    def _check_safety(self, command: str) -> str | None:
        """Check command against safety rules. Returns error string or None if safe."""
        # Check blocked patterns
        for pattern in _BLOCKED_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return f"Error: command blocked by safety policy (matched: {pattern})"

        # Extract base command
        try:
            parts = shlex.split(command)
        except ValueError:
            parts = command.split()

        if not parts:
            return "Error: empty command"

        base_cmd = parts[0].split("/")[-1]  # handle /usr/bin/ls -> ls

        if base_cmd not in _ALLOWED_COMMANDS:
            return (
                f"Error: command '{base_cmd}' is not in the allowed list. "
                f"Allowed: {', '.join(sorted(_ALLOWED_COMMANDS))}"
            )

        if self._strict_path_guard:
            path_guard_error = self._check_path_guard(parts)
            if path_guard_error:
                return path_guard_error

        return None

    def _check_path_guard(self, parts: list[str]) -> str | None:
        """Block path arguments that escape the configured workspace root."""
        if not self._workspace or len(parts) <= 1:
            return None

        workspace_root = self._workspace.resolve()
        redirection_ops = {">", ">>", "<", "1>", "2>", "2>>"}
        candidates: list[str] = []

        for index, token in enumerate(parts[1:], start=1):
            if token in redirection_ops:
                if index + 1 < len(parts):
                    candidates.append(parts[index + 1])
                continue
            if token.startswith("--") and "=" in token:
                _flag, value = token.split("=", 1)
                candidates.append(value)
                continue
            if token.startswith("-"):
                continue
            candidates.append(token)

        for raw_token in candidates:
            if not self._looks_like_path(raw_token):
                continue
            token = raw_token.strip()
            path = Path(token).expanduser()
            if not path.is_absolute():
                path = workspace_root / path
            resolved = path.resolve()
            if not resolved.is_relative_to(workspace_root):
                return (
                    "Error: command blocked by strict_path_guard. "
                    f"Path '{raw_token}' resolves outside workspace '{workspace_root}'."
                )
        return None

    @staticmethod
    def _looks_like_path(token: str) -> bool:
        normalized = token.strip()
        if not normalized or normalized == "-":
            return False
        if "://" in normalized:
            return False
        if normalized.startswith("$"):
            return False
        if normalized in {".", ".."}:
            return True
        if normalized.startswith(("/", "./", "../", "~/")):
            return True
        return "/" in normalized

    @staticmethod
    def _normalize_mode(mode: str) -> SandboxMode:
        normalized = mode.strip().lower()
        if normalized in {"off", "best_effort", "strict"}:
            return normalized  # type: ignore[return-value]
        return "off"

    @staticmethod
    def _normalize_runtime(runtime: str) -> SandboxRuntime:
        normalized = runtime.strip().lower()
        if normalized in {"auto", "bwrap"}:
            return normalized  # type: ignore[return-value]
        return "auto"
