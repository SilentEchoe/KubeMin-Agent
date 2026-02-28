"""Tests for ContentAuditTool semantic summary integration."""

from unittest.mock import AsyncMock

import pytest

from kubemin_agent.agent.tools.content_audit import ContentAuditTool


@pytest.mark.asyncio
async def test_content_audit_all_uses_semantic_summary_for_large_text_and_console() -> None:
    mcp = AsyncMock()

    async def _call_tool(name, args):  # noqa: ANN001
        if name == "take_snapshot":
            return "error banner appears\n" + ("snapshot line\n" * 300)
        if name == "evaluate_script":
            return '[{"src":"https://img.example.com/a.png","alt":"","width":10,"height":10}]'
        if name == "list_console_messages":
            return "WARNING request timeout\n" + ("console line\n" * 300)
        return ""

    mcp.call_tool.side_effect = _call_tool
    tool = ContentAuditTool(mcp)

    result = await tool.execute(check_type="all")

    assert "Content Audit Report" in result
    assert "[Semantic Summary] content_audit_snapshot" in result
    assert "[Semantic Summary] content_audit_console" in result
