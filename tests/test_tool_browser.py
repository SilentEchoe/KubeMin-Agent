"""Tests for BrowserTool semantic summarization behavior."""

from unittest.mock import AsyncMock

import pytest

from kubemin_agent.agent.tools.browser import BrowserTool


@pytest.mark.asyncio
async def test_browser_snapshot_uses_semantic_summary_for_long_output() -> None:
    mcp = AsyncMock()
    mcp.call_tool.return_value = "uid=1 button start\n" + ("very long snapshot content\n" * 300)
    tool = BrowserTool(mcp)

    result = await tool.execute(action="snapshot")

    assert "[Semantic Summary] browser_snapshot" in result
    assert "uid=1 button start" in result


@pytest.mark.asyncio
async def test_browser_console_and_network_use_summary_for_long_output() -> None:
    mcp = AsyncMock()

    async def _call_tool(name, args):  # noqa: ANN001
        if name == "list_console_messages":
            return "ERROR timeout\n" + ("console line\n" * 400)
        if name == "list_network_requests":
            return "HTTP 500 /api/workflow\n" + ("network line\n" * 400)
        return "ok"

    mcp.call_tool.side_effect = _call_tool
    tool = BrowserTool(mcp)

    console_output = await tool.execute(action="console_logs")
    network_output = await tool.execute(action="network")

    assert "[Semantic Summary] browser_console_logs" in console_output
    assert "ERROR timeout" in console_output
    assert "[Semantic Summary] browser_network_requests" in network_output
    assert "HTTP 500 /api/workflow" in network_output
