"""Tests for semantic tool output summarizer."""

from kubemin_agent.agent.tools.summarizer import ToolResultSummarizer


def test_summarizer_keeps_short_text_unchanged() -> None:
    summarizer = ToolResultSummarizer(max_output_chars=200)
    text = "short output line"
    assert summarizer.summarize(text, title="demo") == text


def test_summarizer_extracts_key_signals_from_long_text() -> None:
    summarizer = ToolResultSummarizer(max_output_chars=120, max_signal_lines=3)
    long_text = "\n".join(
        [
            "line 1",
            "Request completed with status 200",
            "ERROR: pod restart failed due to timeout",
            "traceback: sample stack",
            "line tail " + ("x" * 300),
        ]
    )

    result = summarizer.summarize(long_text, title="network")

    assert "[Semantic Summary] network" in result
    assert "key_signals" in result
    assert "ERROR: pod restart failed due to timeout" in result
    assert "tail_excerpt" in result
