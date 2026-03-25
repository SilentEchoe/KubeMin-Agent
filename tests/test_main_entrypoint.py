"""Tests for package __main__ entrypoint."""

from __future__ import annotations

import runpy


def test_main_entrypoint_invokes_app(monkeypatch) -> None:
    called = {"count": 0}

    def _fake_app() -> None:
        called["count"] += 1

    monkeypatch.setattr("kubemin_agent.cli.commands.app", _fake_app)
    runpy.run_module("kubemin_agent.__main__", run_name="__main__")
    assert called["count"] == 1
