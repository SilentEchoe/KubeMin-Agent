"""Tests for global sandbox launcher behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from kubemin_agent.config.schema import Config
from kubemin_agent.sandbox import launcher


def _new_config(tmp_path: Path) -> Config:
    cfg = Config()
    cfg.agents.defaults.workspace = str(tmp_path / "workspace")
    return cfg


def test_strict_mode_fails_when_no_backend(monkeypatch, tmp_path: Path) -> None:
    cfg = _new_config(tmp_path)
    cfg.sandbox.mode = "strict"
    cfg.sandbox.backends = ["container", "bwrap"]

    monkeypatch.delenv("KUBEMIN_AGENT_SANDBOX", raising=False)
    monkeypatch.setattr(launcher.shutil, "which", lambda _name: None)

    with pytest.raises(launcher.SandboxBootstrapError):
        launcher.ensure_process_sandbox(cfg, config_path=tmp_path / "config.json")


def test_no_reexec_when_already_in_sandbox(monkeypatch, tmp_path: Path) -> None:
    cfg = _new_config(tmp_path)
    cfg.sandbox.mode = "strict"

    monkeypatch.setenv("KUBEMIN_AGENT_SANDBOX", "1")

    called = {"exec": False}

    def _fake_execvp(_binary: str, _args: list[str]) -> None:
        called["exec"] = True
        raise AssertionError("execvp should not be called when already in sandbox")

    monkeypatch.setattr(launcher.os, "execvp", _fake_execvp)
    launcher.ensure_process_sandbox(cfg, config_path=tmp_path / "config.json")
    assert called["exec"] is False


def test_container_backend_reexecs_with_python_entrypoint(monkeypatch, tmp_path: Path) -> None:
    cfg = _new_config(tmp_path)
    cfg.sandbox.mode = "strict"
    cfg.sandbox.backends = ["container"]
    cfg.sandbox.container.runtime = "docker"
    cfg.sandbox.container.image = "kubemin-agent:latest"
    cfg.sandbox.network.allowlist = ["api.openai.com"]

    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")

    def _which(name: str) -> str | None:
        if name == "docker":
            return "/usr/bin/docker"
        return None

    monkeypatch.delenv("KUBEMIN_AGENT_SANDBOX", raising=False)
    monkeypatch.setattr(launcher.shutil, "which", _which)
    monkeypatch.setattr(launcher.sys, "argv", ["kubemin-agent", "agent", "-m", "hi"])

    captured: dict[str, object] = {}

    def _fake_execvp(binary: str, args: list[str]) -> None:
        captured["binary"] = binary
        captured["args"] = args
        raise RuntimeError("reexec")

    monkeypatch.setattr(launcher.os, "execvp", _fake_execvp)

    with pytest.raises(RuntimeError, match="reexec"):
        launcher.ensure_process_sandbox(cfg, config_path=config_path)

    assert captured["binary"] == "/usr/bin/docker"
    args = captured["args"]
    assert isinstance(args, list)
    assert "--entrypoint" in args
    assert "python" in args
    assert "kubemin_agent.cli.commands" in args
