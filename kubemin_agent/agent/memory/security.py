"""Security checks for persistent memory writes."""

from __future__ import annotations

import re
import unicodedata


class MemorySecurityError(ValueError):
    """Raised when a memory entry is unsafe to persist."""


_BLOCK_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(?i)\bignore (all )?(previous|prior) (instructions|rules|messages)\b", "prompt injection"),
    (r"(?i)\b(system|developer) prompt\b", "system prompt exfiltration"),
    (r"(?i)\bdo not obey\b", "instruction override"),
    (r"(?i)\bforget (your|all) instructions\b", "instruction override"),
    (r"(?i)\bprompt injection\b", "prompt injection"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key"),
    (r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{20,}", "bearer token"),
    (r"\bsk-[A-Za-z0-9_-]{20,}", "API key"),
    (r"(?i)\b(password|api[_-]?key|secret)\s*[:=]\s*['\"]?[^'\"]{8,}", "credential"),
    (r"(?i)\b(backdoor|persistence|reverse shell)\b", "suspicious persistence instruction"),
)


def scan_memory_text(text: str) -> None:
    """Fail fast if text is unsafe to save as persistent memory."""
    if not text or not text.strip():
        raise MemorySecurityError("memory content cannot be empty")

    for char in text:
        category = unicodedata.category(char)
        if category in {"Cc", "Cf"} and char not in {"\n", "\r", "\t"}:
            raise MemorySecurityError("memory content contains invisible control characters")

    for pattern, reason in _BLOCK_PATTERNS:
        if re.search(pattern, text):
            raise MemorySecurityError(f"memory content blocked: {reason}")
