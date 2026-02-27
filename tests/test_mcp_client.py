"""Tests for MCPClient."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kubemin_agent.agent.tools.mcp_client import MCPClient


@pytest.fixture
def mcp_client():
    """Create a client with sandbox disabled for simpler testing."""
    return MCPClient(headless=True, no_sandbox=True)


@pytest.mark.asyncio
@patch("kubemin_agent.agent.tools.mcp_client.shutil.which")
async def test_start_npx_not_found(mock_which, mcp_client):
    """Test start fails if npx is missing."""
    mock_which.return_value = None
    with pytest.raises(RuntimeError, match="npx not found"):
        await mcp_client.start()


@pytest.mark.asyncio
@patch("kubemin_agent.agent.tools.mcp_client.asyncio.create_subprocess_exec")
@patch("kubemin_agent.agent.tools.mcp_client.shutil.which")
async def test_start_success_and_initialize(mock_which, mock_exec, mcp_client):
    """Test successful start and initialization handshake."""
    mock_which.return_value = "/usr/bin/npx"
    
    mock_process = AsyncMock()
    mock_process.stdin = AsyncMock()
    mock_exec.return_value = mock_process
    
    # We need to mock _send_request and _send_notification directly for this unit test
    # since we don't want to deal with actually wiring up the stdout reader loops in a simple test
    with patch.object(mcp_client, "_send_request", new_callable=AsyncMock) as mock_req, \
         patch.object(mcp_client, "_send_notification", new_callable=AsyncMock) as mock_notif, \
         patch.object(mcp_client, "_read_responses"): # mock out the background reader
         
        mock_req.return_value = {"serverInfo": {"name": "test-server"}}
        
        await mcp_client.start()
        
        assert mcp_client._process == mock_process
        assert mcp_client._initialized is True
        
        mock_req.assert_called_once_with("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "kubemin-agent", "version": "0.1.0"},
        })
        mock_notif.assert_called_once_with("notifications/initialized", {})


@pytest.mark.asyncio
async def test_call_tool_extracts_text(mcp_client):
    """Test that call_tool correctly parses text and image content from MCP server."""
    mcp_client._initialized = True
    
    mock_response = {
        "content": [
            {"type": "text", "text": "Result text here"},
            {"type": "image", "mimeType": "image/png", "data": "base64..."}
        ]
    }
    
    with patch.object(mcp_client, "_send_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_response
        
        result = await mcp_client.call_tool("my_tool", {"arg1": "val1"})
        
        mock_req.assert_called_once_with("tools/call", {
            "name": "my_tool",
            "arguments": {"arg1": "val1"}
        })
        
        assert "Result text here" in result
        assert "[image: image/png]" in result


@pytest.mark.asyncio
async def test_list_tools(mcp_client):
    """Test that list_tools correctly returns the tools array."""
    mcp_client._initialized = True
    
    mock_response = {
        "tools": [
            {"name": "tool_1", "description": "desc 1"},
            {"name": "tool_2", "description": "desc 2"},
        ]
    }
    
    with patch.object(mcp_client, "_send_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_response
        
        tools = await mcp_client.list_tools()
        
        mock_req.assert_called_once_with("tools/list", {})
        assert len(tools) == 2
        assert tools[0]["name"] == "tool_1"


@pytest.mark.asyncio
async def test_send_request_timeout(mcp_client):
    """Test that a request times out correctly."""
    mcp_client._process = MagicMock()
    mcp_client._process.stdin = AsyncMock()
    
    # We mock asyncio.wait_for to simply raise TimeoutError
    with patch("kubemin_agent.agent.tools.mcp_client.asyncio.wait_for", side_effect=asyncio.TimeoutError):
        with pytest.raises(RuntimeError, match="MCP request timed out"):
            await mcp_client._send_request("test_method", {})
        
    assert 1 not in mcp_client._pending


@pytest.mark.asyncio
async def test_stop_cleanup(mcp_client):
    """Test that stop correctly cleans up the process and tasks."""
    mcp_client._initialized = True
    
    mock_process = AsyncMock()
    mcp_client._process = mock_process
    
    # Use a real task so it can be awaited properly
    async def dummy_task():
        await asyncio.sleep(10)
    
    real_task = asyncio.create_task(dummy_task())
    mcp_client._reader_task = real_task
    
    mcp_client._pending[99] = asyncio.Future()
    
    await mcp_client.stop()
    
    assert real_task.cancelled() or real_task.done()
    mock_process.terminate.assert_called_once()
    assert mcp_client._process is None
    assert mcp_client._reader_task is None
    assert not mcp_client._initialized
    assert len(mcp_client._pending) == 0
