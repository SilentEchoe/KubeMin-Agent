"""Kubectl tool for read-only Kubernetes operations."""

from __future__ import annotations

import asyncio
import re
import shlex
from typing import Any

from kubemin_agent.agent.tools.base import Tool

# Read-only kubectl sub-commands
_ALLOWED_SUBCOMMANDS = {
    "get", "describe", "logs", "top", "explain",
    "api-resources", "api-versions", "version",
    "cluster-info", "config view",
}

# Kubectl sub-commands that are always blocked
_BLOCKED_SUBCOMMANDS = {
    "apply", "delete", "patch", "edit", "scale",
    "create", "replace", "rollout", "set",
    "exec", "run", "expose", "label", "annotate",
    "taint", "drain", "cordon", "uncordon",
    "cp", "attach", "port-forward", "proxy",
}

MAX_OUTPUT_LENGTH = 4000
DEFAULT_TIMEOUT = 30


class KubectlTool(Tool):
    """Execute read-only kubectl commands against the configured cluster."""

    def __init__(self, allowed_namespaces: list[str] | None = None) -> None:
        self._allowed_namespaces = allowed_namespaces or []

    @property
    def name(self) -> str:
        return "kubectl"

    @property
    def description(self) -> str:
        ns_hint = ""
        if self._allowed_namespaces:
            ns_hint = f" Allowed namespaces: {', '.join(self._allowed_namespaces)}."
        return (
            "Execute read-only kubectl commands (get, describe, logs, top, explain). "
            f"Write operations (apply, delete, patch, etc.) are blocked.{ns_hint}"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": (
                        "The kubectl arguments (without 'kubectl' prefix). "
                        "Example: 'get pods -n default' or 'describe deploy/nginx'."
                    ),
                },
                "namespace": {
                    "type": "string",
                    "description": "Target namespace (overrides -n in command if provided).",
                },
            },
            "required": ["command"],
        }

    async def execute(self, *, command: str, namespace: str = "") -> str:
        # Safety validation
        safety_error = self._check_safety(command)
        if safety_error:
            return safety_error

        # Build full command
        full_cmd = self._build_command(command, namespace)

        try:
            proc = await asyncio.create_subprocess_shell(
                full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=DEFAULT_TIMEOUT
            )
        except asyncio.TimeoutError:
            proc.kill()
            return f"Error: kubectl timed out after {DEFAULT_TIMEOUT}s"
        except Exception as e:
            return f"Error executing kubectl: {e}"

        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()

        # Filter sensitive data from output
        stdout_text = self._filter_secrets(stdout_text)

        parts: list[str] = []
        if stdout_text:
            parts.append(stdout_text)
        if stderr_text:
            parts.append(f"[stderr] {stderr_text}")
        if proc.returncode != 0:
            parts.append(f"[exit_code: {proc.returncode}]")

        result = "\n".join(parts) if parts else "(no output)"

        if len(result) > MAX_OUTPUT_LENGTH:
            result = (
                result[:MAX_OUTPUT_LENGTH]
                + f"\n... (truncated, total {len(result)} chars)"
            )

        return result

    def _build_command(self, command: str, namespace: str) -> str:
        """Build the full kubectl command with namespace injection."""
        parts = shlex.split(command) if command else []

        # If namespace provided and not already in command, inject it
        if namespace and "-n" not in parts and "--namespace" not in parts:
            parts.extend(["-n", namespace])

        return "kubectl " + " ".join(shlex.quote(p) for p in parts)

    def _check_safety(self, command: str) -> str | None:
        """Validate command is read-only. Returns error string or None."""
        parts = command.strip().split()
        if not parts:
            return "Error: empty kubectl command"

        # Extract the sub-command (first arg)
        sub_cmd = parts[0].lower()

        if sub_cmd in _BLOCKED_SUBCOMMANDS:
            return (
                f"Error: kubectl '{sub_cmd}' is a write operation and is blocked. "
                f"Only read-only commands are allowed: {', '.join(sorted(_ALLOWED_SUBCOMMANDS))}"
            )

        if sub_cmd not in _ALLOWED_SUBCOMMANDS:
            return (
                f"Error: kubectl '{sub_cmd}' is not recognized as a safe command. "
                f"Allowed: {', '.join(sorted(_ALLOWED_SUBCOMMANDS))}"
            )

        # Namespace restriction
        if self._allowed_namespaces:
            ns = self._extract_namespace(parts)
            if ns and ns not in self._allowed_namespaces:
                return (
                    f"Error: namespace '{ns}' is not allowed. "
                    f"Allowed: {', '.join(self._allowed_namespaces)}"
                )

        return None

    def _extract_namespace(self, parts: list[str]) -> str | None:
        """Extract namespace from command args."""
        for i, p in enumerate(parts):
            if p in ("-n", "--namespace") and i + 1 < len(parts):
                return parts[i + 1]
            if p.startswith("-n="):
                return p[3:]
            if p.startswith("--namespace="):
                return p[12:]
        return None

    @staticmethod
    def _filter_secrets(output: str) -> str:
        """Mask potential secret data in output."""
        # Mask base64 data blocks that look like secret values
        output = re.sub(
            r"(data:\s*\n)((?:\s+\S+:\s+)\S{20,}\n)+",
            r"\1    [SECRET DATA MASKED]\n",
            output,
        )
        return output
