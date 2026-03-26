"""KubeMin-Cli tool for querying KubeMin platform resources."""

from __future__ import annotations

import asyncio
import re
import shlex
from typing import Any

from kubemin_agent.agent.tools.base import Tool

# Read-only subcommands that are allowed
_ALLOWED_SUBCOMMANDS = {
    "get", "list", "describe", "status", "version", "health",
    "inspect", "show", "info", "check", "logs",
}

# Subcommands that are always blocked (write/mutate operations)
_BLOCKED_SUBCOMMANDS = {
    "delete", "apply", "create", "update", "scale", "restart",
    "patch", "edit", "rollback", "drain", "cordon", "uncordon",
    "exec", "run", "install", "uninstall", "upgrade",
}

# Dangerous patterns in arguments
_BLOCKED_PATTERNS = [
    r"\bsudo\b",
    r"\brm\s+-rf\b",
    r"\|.*(?:sh|bash|zsh)\b",
    r";.*(?:sh|bash|zsh)\b",
    r"\beval\b",
    r"\bexec\b",
    r">\s*/",
]

MAX_OUTPUT_LENGTH = 4000
DEFAULT_TIMEOUT = 30


class KubeMinCliTool(Tool):
    """Execute read-only kubemin-cli commands to query platform resources."""

    def __init__(
        self,
        api_base: str = "",
        namespace: str = "",
    ) -> None:
        self._api_base = api_base
        self._namespace = namespace

    @property
    def name(self) -> str:
        return "kubemin_cli"

    @property
    def description(self) -> str:
        return (
            "Execute kubemin-cli commands to query KubeMin platform resources. "
            "Supports read-only operations: get, list, describe, status, health, version, etc. "
            "Write operations (create, delete, update, apply, scale) are blocked. "
            "Use this to inspect applications, workflows, services, and platform configuration."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": (
                        "The kubemin-cli command to execute, e.g. "
                        "'kubemin-cli get apps', 'kubemin-cli list workflows --status failed', "
                        "'kubemin-cli health', 'kubemin-cli describe app my-app'."
                    ),
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default 30, max 120).",
                },
            },
            "required": ["command"],
        }

    async def execute(self, **kwargs: Any) -> str:
        command = kwargs.get("command")
        if not isinstance(command, str):
            return "Error: command must be a string"
        timeout_raw = kwargs.get("timeout", DEFAULT_TIMEOUT)
        if not isinstance(timeout_raw, int):
            return "Error: timeout must be an integer"
        timeout = timeout_raw
        timeout = min(max(timeout, 1), 120)

        # Safety checks
        safety_error = self._check_safety(command)
        if safety_error:
            return safety_error

        # Inject default flags
        full_command = self._inject_defaults(command)

        try:
            proc = await asyncio.create_subprocess_shell(
                full_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            return f"Error: command timed out after {timeout}s"
        except Exception as e:
            return f"Error executing kubemin-cli command: {e}"

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
            result = (
                result[:MAX_OUTPUT_LENGTH]
                + f"\n... (truncated, total {len(result)} chars)"
            )

        return result

    def _check_safety(self, command: str) -> str | None:
        """Validate command is read-only and safe. Returns error string or None."""
        # Check blocked patterns
        for pattern in _BLOCKED_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return f"Error: command blocked by safety policy (matched: {pattern})"

        # Extract parts
        try:
            parts = shlex.split(command)
        except ValueError:
            parts = command.split()

        if not parts:
            return "Error: empty command"

        # Normalize: strip leading 'kubemin-cli' or 'kubemin' if present
        base = parts[0].split("/")[-1]
        if base in ("kubemin-cli", "kubemin"):
            parts = parts[1:]
        elif base not in _ALLOWED_SUBCOMMANDS:
            return (
                "Error: command must start with 'kubemin-cli'. "
                "Example: 'kubemin-cli get apps'"
            )

        if not parts:
            return "Error: no subcommand provided. Example: 'kubemin-cli get apps'"

        subcommand = parts[0].lower()

        if subcommand in _BLOCKED_SUBCOMMANDS:
            return (
                f"Error: subcommand '{subcommand}' is blocked (write operation). "
                f"Only read-only subcommands are allowed: "
                f"{', '.join(sorted(_ALLOWED_SUBCOMMANDS))}"
            )

        if subcommand not in _ALLOWED_SUBCOMMANDS:
            return (
                f"Error: subcommand '{subcommand}' is not in the allowed list. "
                f"Allowed: {', '.join(sorted(_ALLOWED_SUBCOMMANDS))}"
            )

        return None

    def _inject_defaults(self, command: str) -> str:
        """Inject default --api-base and --namespace flags if not already present."""
        cmd = command

        if self._api_base and "--api-base" not in cmd and "--server" not in cmd:
            cmd = f"{cmd} --api-base {shlex.quote(self._api_base)}"

        if self._namespace and "--namespace" not in cmd and "-n " not in cmd:
            cmd = f"{cmd} --namespace {shlex.quote(self._namespace)}"

        return cmd
