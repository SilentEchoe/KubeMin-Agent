"""Sandbox helpers for tool command execution."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SandboxMode = Literal["off", "best_effort", "strict"]
SandboxRuntime = Literal["auto", "bwrap"]


@dataclass(frozen=True)
class SandboxPolicy:
    """Sandbox policy for command execution."""

    mode: SandboxMode = "off"
    runtime: SandboxRuntime = "auto"
    allow_network: bool = False


class SandboxUnavailableError(RuntimeError):
    """Raised when sandbox execution is required but unavailable."""


class SandboxRunner:
    """Build sandboxed command invocations for shell execution."""

    def __init__(self, workspace: Path, policy: SandboxPolicy) -> None:
        self._workspace = workspace.resolve()
        self._policy = policy

    @property
    def policy(self) -> SandboxPolicy:
        return self._policy

    def build_command(self, command: str) -> list[str] | None:
        """
        Build a sandbox wrapper command for the input shell command.

        Returns:
            Wrapped command for subprocess_exec, or None when sandbox is disabled
            or unavailable in best-effort mode.

        Raises:
            SandboxUnavailableError: If mode is strict and runtime is unavailable.
        """
        if self._policy.mode == "off":
            return None

        runtime = self._resolve_runtime()
        if not runtime:
            if self._policy.mode == "strict":
                raise SandboxUnavailableError(
                    "Sandbox runtime 'bwrap' is not available, cannot run in strict mode."
                )
            return None

        return self._build_bwrap_command(runtime, command)

    def _resolve_runtime(self) -> str | None:
        # Currently bwrap is the only runtime implementation.
        if self._policy.runtime in {"auto", "bwrap"}:
            return shutil.which("bwrap")
        return None

    def _build_bwrap_command(self, bwrap_bin: str, command: str) -> list[str]:
        wrapped: list[str] = [
            bwrap_bin,
            "--die-with-parent",
            "--new-session",
            "--unshare-pid",
            "--unshare-ipc",
            "--unshare-uts",
        ]

        if not self._policy.allow_network:
            wrapped.append("--unshare-net")

        wrapped.extend(
            [
                "--ro-bind",
                "/",
                "/",
                "--dev",
                "/dev",
                "--proc",
                "/proc",
                "--tmpfs",
                "/tmp",
                "--bind",
                str(self._workspace),
                str(self._workspace),
                "--chdir",
                str(self._workspace),
                "sh",
                "-lc",
                command,
            ]
        )
        return wrapped
