"""Tests for configuration loader helpers."""

from __future__ import annotations

from pathlib import Path

from kubemin_agent.config.loader import ensure_workspace, load_config, save_default_config


def test_load_config_from_valid_file(tmp_path: Path) -> None:
    config_file = tmp_path / "config.json"
    config_file.write_text(
        """
{
  "agents": {
    "defaults": {
      "workspace": "/tmp/test-workspace",
      "model": "test-model"
    }
  }
}
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_file)
    assert config.agents.defaults.workspace == "/tmp/test-workspace"
    assert config.agents.defaults.model == "test-model"


def test_load_config_invalid_file_falls_back_to_defaults(tmp_path: Path) -> None:
    config_file = tmp_path / "broken.json"
    config_file.write_text("{ invalid-json ", encoding="utf-8")
    config = load_config(config_file)
    assert config.agents.defaults.model


def test_save_default_config_and_ensure_workspace(tmp_path: Path) -> None:
    config_file = tmp_path / "conf" / "config.json"
    saved_path = save_default_config(config_file)
    assert saved_path.exists()

    config = load_config(saved_path)
    config.agents.defaults.workspace = str(tmp_path / "workspace")
    workspace = ensure_workspace(config)
    assert workspace.exists()
    assert (workspace / "memory").exists()
    assert (workspace / "skills").exists()
