"""Tests for process-level egress guard."""

from __future__ import annotations

import socket

import pytest

from kubemin_agent.config.schema import Config
from kubemin_agent.sandbox import egress


@pytest.fixture(autouse=True)
def _reset_guard(monkeypatch):
    monkeypatch.setattr(egress, "_GUARD_INSTALLED", False)
    original = socket.getaddrinfo
    yield
    socket.getaddrinfo = original


def test_strict_default_deny_requires_proxy_url() -> None:
    cfg = Config()
    cfg.sandbox.mode = "strict"
    cfg.sandbox.network.default_deny = True
    cfg.sandbox.network.enforce_proxy = True
    cfg.sandbox.network.proxy_url = ""

    with pytest.raises(egress.EgressGuardError):
        egress.install_egress_guard(cfg)


def test_proxy_enforcement_injects_env_and_blocks_direct(monkeypatch) -> None:
    cfg = Config()
    cfg.sandbox.mode = "strict"
    cfg.sandbox.network.default_deny = True
    cfg.sandbox.network.enforce_proxy = True
    cfg.sandbox.network.proxy_url = "http://proxy.local:3128"
    cfg.sandbox.network.allowlist = ["api.openai.com", "api.telegram.org"]

    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: [])

    egress.install_egress_guard(cfg)

    assert egress.os.environ["HTTP_PROXY"] == "http://proxy.local:3128"
    assert egress.os.environ["HTTPS_PROXY"] == "http://proxy.local:3128"
    assert egress.os.environ["KUBEMIN_AGENT_EGRESS_ALLOWLIST"] == "api.openai.com,api.telegram.org"

    # Direct connection to proxy host is allowed.
    socket.getaddrinfo("proxy.local", 3128)

    # Direct DNS resolution to non-local/non-proxy host is blocked.
    with pytest.raises(egress.EgressGuardError):
        socket.getaddrinfo("example.com", 443)
