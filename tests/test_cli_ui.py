"""Tests for CLI interactive UI helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from rich.console import Console

from kubemin_agent.cli import ui


class DummyRuntime:
    def __init__(self) -> None:
        self.model = "stub-model"
        self.messages: list[str] = []

    async def handle_message(self, channel: str, chat_id: str, text: str) -> str:
        self.messages.append(f"{channel}:{chat_id}:{text}")
        return f"reply:{text}"


def _patch_prompt_session(monkeypatch: pytest.MonkeyPatch, inputs: list[str]) -> None:
    class FakePromptSession:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            self._inputs = iter(inputs)

        async def prompt_async(self, *args, **kwargs) -> str:  # noqa: ANN002, ANN003
            try:
                return next(self._inputs)
            except StopIteration as exc:
                raise EOFError from exc

    monkeypatch.setattr(ui, "PromptSession", FakePromptSession)


def _patch_skills_loader(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Skill:
        def __init__(self, name: str) -> None:
            self.name = name

    class FakeSkillsLoader:
        def __init__(self, workspace: Path) -> None:
            self._workspace = workspace

        @property
        def skill_names(self) -> list[str]:
            return ["patrol"]

        def build_skills_summary(self) -> str:
            return "- patrol: cluster巡检"

        def get_always_skills(self) -> list[_Skill]:
            return [_Skill("baseline")]

    monkeypatch.setattr(ui, "SkillsLoader", FakeSkillsLoader)


def test_create_startup_panel_uses_tilde_for_home_workspace(tmp_path: Path) -> None:
    runtime = DummyRuntime()
    workspace = Path.home() / "demo_workspace"
    panel = ui.create_startup_panel(runtime, workspace)
    assert "KubeMin-Agent" in panel
    assert "stub-model" in panel
    assert "~/" in panel


@pytest.mark.asyncio
async def test_run_interactive_ui_help_clear_and_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = DummyRuntime()
    console = Console(record=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    _patch_prompt_session(monkeypatch, ["/help", "/clear", "/exit"])
    _patch_skills_loader(monkeypatch)
    clear_calls: list[str] = []
    monkeypatch.setattr(ui.os, "system", lambda cmd: clear_calls.append(cmd) or 0)

    await ui.run_interactive_ui(runtime, workspace, console)
    output = console.export_text()
    assert "可用命令" in output
    assert clear_calls
    assert runtime.messages == []


@pytest.mark.asyncio
async def test_run_interactive_ui_skills_and_message_roundtrip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = DummyRuntime()
    console = Console(record=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    _patch_prompt_session(monkeypatch, ["/skills", "hello", "/model", "/exit"])
    _patch_skills_loader(monkeypatch)

    await ui.run_interactive_ui(runtime, workspace, console)
    output = console.export_text()
    assert "已加载技能" in output
    assert "reply:hello" in output
    assert "切换模型功能尚在开发中" in output
    assert runtime.messages == ["cli:interactive:hello"]
