"""Shell command execution tool with safety constraints."""

from __future__ import annotations

import asyncio
import re
import shlex
from pathlib import Path
from typing import Any

from kubemin_agent.agent.tools.base import Tool
from kubemin_agent.agent.tools.sandbox import (
    SandboxPolicy,
    SandboxRunner,
    SandboxUnavailableError,
)

# Whitelisted command prefixes
_ALLOWED_COMMANDS = {
    "ls", "cat", "echo", "grep", "find", "wc", "head", "tail",
    "pwd", "env", "date", "curl", "wget",
    "git",
    "kubectl", "helm",
    "sort", "uniq", "diff", "tr", "cut", "awk", "sed",
    "du", "df", "file", "which", "whoami", "uname",
    "tar", "zip", "unzip", "gzip", "gunzip",
    "jq", "yq",
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
        sandbox_mode: str = "off",
        sandbox_runtime: str = "auto",
        sandbox_allow_network: bool = False,
    ) -> None:
        self._workspace = workspace.resolve() if workspace else None
        self._default_timeout = min(max(default_timeout, 1), 120)
        self._restrict_to_workspace = restrict_to_workspace and self._workspace is not None
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

    async def execute(self, *, command: str, timeout: int | None = None) -> str:
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

        return None

    @staticmethod
    def _normalize_mode(mode: str) -> str:
        normalized = mode.strip().lower()
        if normalized in {"off", "best_effort", "strict"}:
            return normalized
        return "off"

    @staticmethod
    def _normalize_runtime(runtime: str) -> str:
        normalized = runtime.strip().lower()
        if normalized in {"auto", "bwrap"}:
            return normalized
        return "auto"
