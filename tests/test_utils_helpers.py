"""Tests for shared utility helper functions."""

from __future__ import annotations

import kubemin_agent.utils as utils
from kubemin_agent.utils.helpers import format_error, sanitize_session_key, truncate_output


def test_utils_exports() -> None:
    assert hasattr(utils, "truncate_output")
    assert hasattr(utils, "sanitize_session_key")
    assert hasattr(utils, "format_error")


def test_truncate_output_behaviors() -> None:
    short = "hello"
    assert truncate_output(short, max_length=10) == short

    long_text = "a" * 30
    truncated = truncate_output(long_text, max_length=10)
    assert "truncated" in truncated
    assert truncated.startswith("aaaaa")
    assert truncated.endswith("aaaaa")


def test_sanitize_session_key_and_format_error() -> None:
    assert sanitize_session_key("telegram:chat/123") == "telegram_chat_123"
    assert format_error(ValueError("bad input")) == "ValueError: bad input"
