"""Process-level sandbox launcher and fail-closed preflight."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Literal

from loguru import logger

from kubemin_agent.config.loader import DEFAULT_CONFIG_FILE
from kubemin_agent.config.schema import Config

SandboxMode = Literal["off", "best_effort", "strict"]
SandboxBackend = Literal["container", "bwrap"]

_SANDBOX_FLAG = "KUBEMIN_AGENT_SANDBOX"
_SANDBOX_BACKEND = "KUBEMIN_AGENT_SANDBOX_BACKEND"


class SandboxBootstrapError(RuntimeError):
    """Raised when sandbox preflight fails in strict mode."""


def ensure_process_sandbox(config: Config, config_path: Path | None = None) -> None:
    """
    Ensure current process runs inside global sandbox according to config.

    In strict mode, this function fails closed when no sandbox backend is available.
    """
    mode = _normalize_mode(getattr(getattr(config, "sandbox", None), "mode", "off"))
    if mode == "off":
        return

    if _is_in_sandbox():
        return

    selected = _select_backend(config)
    if selected is None:
        msg = (
            "Global sandbox is enabled but no backend is available. "
            "Checked backends: " + ", ".join(getattr(config.sandbox, "backends", []))
        )
        if mode == "strict":
            raise SandboxBootstrapError(msg)
        logger.warning(msg)
        return

    backend, backend_bin = selected
    logger.info(f"Relaunching current command inside sandbox backend: {backend}")

    if backend == "container":
        cmd = _build_container_command(
            config=config,
            config_path=config_path,
            runtime_bin=backend_bin,
        )
    else:
        cmd = _build_bwrap_command(config=config, config_path=config_path, bwrap_bin=backend_bin)

    logger.debug("Sandbox command: {}", " ".join(cmd))
    os.execvp(cmd[0], cmd)


def _is_in_sandbox() -> bool:
    return os.environ.get(_SANDBOX_FLAG) == "1"


def _normalize_mode(mode: str) -> SandboxMode:
    normalized = (mode or "").strip().lower()
    if normalized in {"off", "best_effort", "strict"}:
        return normalized  # type: ignore[return-value]
    return "off"


def _select_backend(config: Config) -> tuple[SandboxBackend, str] | None:
    backends = list(getattr(config.sandbox, "backends", []))
    runtime_name = getattr(config.sandbox.container, "runtime", "docker")

    for backend in backends:
        if backend == "container":
            runtime_bin = shutil.which(runtime_name)
            if runtime_bin:
                return "container", runtime_bin
        elif backend == "bwrap":
            bwrap_bin = shutil.which("bwrap")
            if bwrap_bin:
                return "bwrap", bwrap_bin
    return None


def _build_container_command(
    *,
    config: Config,
    config_path: Path | None,
    runtime_bin: str,
) -> list[str]:
    container_cfg = config.sandbox.container
    config_src = _resolve_config_path(config_path)
    if not config_src.exists():
        raise SandboxBootstrapError(
            f"Config file not found for sandbox mount: {config_src}. "
            "Please run `kubemin-agent onboard` first or pass --config."
        )

    workspace = config.workspace_path.resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    args = _rewrite_cli_args(sys.argv[1:], Path(container_cfg.config_mount))

    cmd: list[str] = [runtime_bin, "run", "--rm", "-i"]
    if sys.stdin.isatty():
        cmd.append("-t")

    if container_cfg.read_only_rootfs:
        cmd.append("--read-only")

    cmd.extend(
        [
            "--tmpfs",
            "/tmp",
            "--tmpfs",
            "/run",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--pids-limit",
            str(container_cfg.pids_limit),
            "--memory",
            container_cfg.memory_limit,
            "--cpus",
            container_cfg.cpu_limit,
            "-e",
            f"{_SANDBOX_FLAG}=1",
            "-e",
            f"{_SANDBOX_BACKEND}=container",
            "-e",
            f"KUBEMIN_AGENT_EGRESS_ALLOWLIST={','.join(config.sandbox.network.allowlist)}",
            "-v",
            f"{workspace}:{container_cfg.workspace_mount}",
            "-v",
            f"{config_src.resolve()}:{container_cfg.config_mount}:ro",
            "--entrypoint",
            "python",
            container_cfg.image,
            "-m",
            "kubemin_agent.cli.commands",
            *args,
        ]
    )
    return cmd


def _build_bwrap_command(*, config: Config, config_path: Path | None, bwrap_bin: str) -> list[str]:
    config_src = _resolve_config_path(config_path)
    if not config_src.exists():
        raise SandboxBootstrapError(
            f"Config file not found for sandbox mount: {config_src}. "
            "Please run `kubemin-agent onboard` first or pass --config."
        )

    workspace = config.workspace_path.resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    args = _rewrite_cli_args(sys.argv[1:], config_src)
    python_bin = shutil.which("python3") or shutil.which("python")
    if not python_bin:
        raise SandboxBootstrapError("python3 is required for bwrap backend.")

    cmd: list[str] = [
        bwrap_bin,
        "--die-with-parent",
        "--new-session",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
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
        str(workspace),
        str(workspace),
        "--chdir",
        str(workspace),
        "/usr/bin/env",
        f"{_SANDBOX_FLAG}=1",
        f"{_SANDBOX_BACKEND}=bwrap",
        f"KUBEMIN_AGENT_EGRESS_ALLOWLIST={','.join(config.sandbox.network.allowlist)}",
        python_bin,
        "-m",
        "kubemin_agent.cli.commands",
        *args,
    ]
    return cmd


def _resolve_config_path(config_path: Path | None) -> Path:
    return (config_path or DEFAULT_CONFIG_FILE).expanduser().resolve()


def _rewrite_cli_args(args: list[str], config_mount_path: Path) -> list[str]:
    rewritten = list(args)

    # Replace explicit --config / -c options with the sandbox-mounted path.
    for idx, token in enumerate(rewritten):
        if token == "--config" and idx + 1 < len(rewritten):
            rewritten[idx + 1] = str(config_mount_path)
            return rewritten
        if token == "-c" and idx + 1 < len(rewritten):
            rewritten[idx + 1] = str(config_mount_path)
            return rewritten
        if token.startswith("--config="):
            rewritten[idx] = f"--config={config_mount_path}"
            return rewritten

    rewritten.extend(["--config", str(config_mount_path)])
    return rewritten
