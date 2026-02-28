"""Semantic summarizer for large tool outputs."""

from __future__ import annotations

import re

_DEFAULT_SIGNAL_PATTERNS = [
    r"\berror\b",
    r"\bexception\b",
    r"\bfail(?:ed|ure)?\b",
    r"\btimeout\b",
    r"\bwarn(?:ing)?\b",
    r"\btraceback\b",
    r"\b[45]\d\d\b",
    r"\bblocked\b",
    r"\bdenied\b",
    r"\bnot found\b",
    r"\buid\b",
    r"\bnetwork\b",
    r"\bconsole\b",
]


class ToolResultSummarizer:
    """Summarize long tool outputs while preserving key operational signals."""

    def __init__(
        self,
        max_output_chars: int = 1200,
        max_signal_lines: int = 10,
        head_chars: int = 360,
        tail_chars: int = 240,
    ) -> None:
        self.max_output_chars = max(200, max_output_chars)
        self.max_signal_lines = max(1, max_signal_lines)
        self.head_chars = max(120, head_chars)
        self.tail_chars = max(80, tail_chars)
        self._default_patterns = [re.compile(p, re.IGNORECASE) for p in _DEFAULT_SIGNAL_PATTERNS]

    def summarize(
        self,
        text: str,
        *,
        title: str = "tool_output",
        extra_signal_patterns: list[str] | None = None,
    ) -> str:
        """Return original text when short; otherwise return structured semantic summary."""
        clean = (text or "").strip()
        if len(clean) <= self.max_output_chars:
            return clean

        lines = [line.strip() for line in clean.splitlines() if line.strip()]
        signals = self._extract_signal_lines(lines, extra_signal_patterns)

        summary_lines: list[str] = [
            f"[Semantic Summary] {title}",
            f"- total_chars: {len(clean)}",
            f"- total_lines: {len(lines)}",
        ]

        if signals:
            summary_lines.append("- key_signals:")
            for line in signals:
                summary_lines.append(f"  - {line}")

        head = clean[: self.head_chars]
        tail = clean[-self.tail_chars :]

        summary_lines.append("- head_excerpt:")
        summary_lines.append(self._block(head))
        summary_lines.append("- tail_excerpt:")
        summary_lines.append(self._block(tail))

        return "\n".join(summary_lines)

    def _extract_signal_lines(
        self,
        lines: list[str],
        extra_signal_patterns: list[str] | None,
    ) -> list[str]:
        patterns = list(self._default_patterns)
        if extra_signal_patterns:
            patterns.extend(re.compile(p, re.IGNORECASE) for p in extra_signal_patterns)

        found: list[str] = []
        seen: set[str] = set()
        for line in lines:
            if not line:
                continue
            if len(found) >= self.max_signal_lines:
                break

            if any(pattern.search(line) for pattern in patterns):
                normalized = line[:220]
                if normalized in seen:
                    continue
                seen.add(normalized)
                found.append(normalized)

        return found

    @staticmethod
    def _block(text: str) -> str:
        text = text.strip()
        if not text:
            return "  (empty)"
        return "\n".join(f"  {line}" for line in text.splitlines())
