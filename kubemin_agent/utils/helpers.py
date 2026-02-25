"""Common utility functions."""

import re


def truncate_output(text: str, max_length: int = 4000) -> str:
    """
    Truncate text output to prevent context overflow.

    Args:
        text: Text to truncate.
        max_length: Maximum allowed length.

    Returns:
        Truncated text with indicator if truncated.
    """
    if len(text) <= max_length:
        return text
    half = max_length // 2
    return text[:half] + f"\n\n... [truncated {len(text) - max_length} chars] ...\n\n" + text[-half:]


def sanitize_session_key(key: str) -> str:
    """
    Sanitize a session key for use as a filename.

    Args:
        key: Raw session key.

    Returns:
        Sanitized key safe for filesystem use.
    """
    return re.sub(r"[^a-zA-Z0-9_-]", "_", key)


def format_error(error: Exception) -> str:
    """
    Format an exception for display.

    Args:
        error: The exception to format.

    Returns:
        Human-readable error string.
    """
    error_type = type(error).__name__
    return f"{error_type}: {str(error)}"
