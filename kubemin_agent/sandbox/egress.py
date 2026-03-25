"""Process-level outbound egress guard with proxy enforcement."""

from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

from loguru import logger

from kubemin_agent.config.schema import Config

_GUARD_INSTALLED = False


class EgressGuardError(RuntimeError):
    """Raised when egress guard cannot be enforced in strict mode."""


def install_egress_guard(config: Config) -> None:
    """
    Install process-level egress guard according to global sandbox config.

    In strict mode + default_deny policy, missing proxy configuration is treated
    as a startup error.
    """
    global _GUARD_INSTALLED
    if _GUARD_INSTALLED:
        return

    mode = _normalize_mode(getattr(getattr(config, "sandbox", None), "mode", "off"))
    if mode == "off":
        return

    network_cfg = getattr(getattr(config, "sandbox", None), "network", None)
    if network_cfg is None:
        return

    default_deny = bool(getattr(network_cfg, "default_deny", True))
    enforce_proxy = bool(getattr(network_cfg, "enforce_proxy", True))
    proxy_url = _normalize_proxy_url(getattr(network_cfg, "proxy_url", ""))
    allowlist = _normalize_allowlist(getattr(network_cfg, "allowlist", []) or [])

    if not default_deny:
        return

    if enforce_proxy:
        if not proxy_url:
            if mode == "strict":
                raise EgressGuardError(
                    "Sandbox network policy requires proxy_url in strict mode "
                    "(sandbox.network.proxy_url)."
                )
            logger.warning("Proxy URL missing, skipping strict egress proxy enforcement.")
            return
        _inject_proxy_env(proxy_url)
        allowed_direct_hosts = _base_local_hosts()
        proxy_host = _extract_proxy_host(proxy_url)
        if proxy_host:
            allowed_direct_hosts.add(proxy_host)
        else:
            if mode == "strict":
                raise EgressGuardError(
                    f"Invalid sandbox.network.proxy_url: {proxy_url}"
                )
    else:
        allowed_direct_hosts = _base_local_hosts()
        allowed_direct_hosts.update(allowlist)

    allowlist_csv = ",".join(allowlist)
    os.environ["KUBEMIN_AGENT_EGRESS_ALLOWLIST"] = allowlist_csv
    _install_socket_guard(allowed_direct_hosts)
    _GUARD_INSTALLED = True
    logger.info(
        "Egress guard installed (default_deny={}, enforce_proxy={}, direct_hosts={})",
        default_deny,
        enforce_proxy,
        sorted(allowed_direct_hosts),
    )


def _inject_proxy_env(proxy_url: str) -> None:
    os.environ["HTTP_PROXY"] = proxy_url
    os.environ["HTTPS_PROXY"] = proxy_url
    os.environ["ALL_PROXY"] = proxy_url


def _extract_proxy_host(proxy_url: str) -> str:
    parsed = urlparse(proxy_url)
    return (parsed.hostname or "").lower()


def _normalize_allowlist(allowlist: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in allowlist:
        host = (item or "").strip().lower()
        if not host:
            continue
        host = host.split("://", 1)[-1]
        host = host.split("/", 1)[0]
        host = host.split(":", 1)[0]
        if host and host not in seen:
            normalized.append(host)
            seen.add(host)
    return normalized


def _normalize_mode(mode: object) -> str:
    if not isinstance(mode, str):
        return "off"
    normalized = mode.strip().lower()
    if normalized in {"off", "best_effort", "strict"}:
        return normalized
    return "off"


def _normalize_proxy_url(proxy_url: object) -> str:
    if not isinstance(proxy_url, str):
        return ""
    return proxy_url.strip()


def _base_local_hosts() -> set[str]:
    return {"localhost", "127.0.0.1", "::1"}


def _install_socket_guard(allowed_hosts: set[str]) -> None:
    original_getaddrinfo = socket.getaddrinfo

    def guarded_getaddrinfo(host, *args, **kwargs):
        if isinstance(host, str):
            norm = host.strip().lower().strip("[]")
            if norm and norm not in allowed_hosts:
                raise EgressGuardError(
                    f"Direct outbound DNS resolution is blocked by sandbox policy: {host}"
                )
        return original_getaddrinfo(host, *args, **kwargs)

    socket.getaddrinfo = guarded_getaddrinfo
