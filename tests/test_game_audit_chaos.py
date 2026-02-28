import pytest
from unittest.mock import AsyncMock, patch
from kubemin_agent.agent.tools.browser import BrowserTool

@pytest.mark.asyncio
async def test_mock_network():
    mcp_mock = AsyncMock()
    mcp_mock.call_tool.return_value = "Network mocking applied"
    
    tool = BrowserTool(mcp_mock)
    
    res = await tool.execute(action="mock_network", value='{"/api/inventory":[]}')
    
    assert "Network mocking applied" in res
    mcp_mock.call_tool.assert_called_once()
    
    args, kwargs = mcp_mock.call_tool.call_args
    assert args[0] == "evaluate_script"
    
    js_code = args[1]["function"]
    assert "window.__mockData = {\"/api/inventory\":[]};" in js_code
    assert "window.fetch = async function" in js_code

@pytest.mark.asyncio
async def test_throttle_network():
    mcp_mock = AsyncMock()
    mcp_mock.call_tool.return_value = "Network throttled"
    
    tool = BrowserTool(mcp_mock)
    res = await tool.execute(action="throttle_network", value="5000")
    
    assert "Network throttled" in res
    args, kwargs = mcp_mock.call_tool.call_args
    js_code = args[1]["function"]
    assert "window.__throttleMs = parseInt(5000)" in js_code
    assert "setTimeout(r, window.__throttleMs)" in js_code

@pytest.mark.asyncio
async def test_disconnect_network():
    mcp_mock = AsyncMock()
    mcp_mock.call_tool.return_value = "Network disconnected"
    
    tool = BrowserTool(mcp_mock)
    res = await tool.execute(action="disconnect_network")
    
    assert "Network disconnected" in res
    args, kwargs = mcp_mock.call_tool.call_args
    js_code = args[1]["function"]
    assert "throw new TypeError(\"Failed to fetch\")" in js_code
    assert "window.fetch = async function" in js_code
