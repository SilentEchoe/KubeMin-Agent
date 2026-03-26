"""Tests for MCPClient."""

import asyncio
from pathlib import Path
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
    mcp_client._process.stdin = MagicMock()
    mcp_client._process.stdin.write = MagicMock()
    mcp_client._process.stdin.drain = AsyncMock()

    # We mock asyncio.wait_for to simply raise TimeoutError
    with patch("kubemin_agent.agent.tools.mcp_client.asyncio.wait_for", side_effect=asyncio.TimeoutError):
        with pytest.raises(RuntimeError, match="MCP request timed out"):
            await mcp_client._send_request("test_method", {})

    assert 1 not in mcp_client._pending


@pytest.mark.asyncio
async def test_stop_cleanup(mcp_client):
    """Test that stop correctly cleans up the process and tasks."""
    mcp_client._initialized = True

    mock_process = MagicMock()
    mock_process.terminate = MagicMock()
    mock_process.wait = AsyncMock(return_value=0)
    mock_process.kill = MagicMock()
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


def test_detect_container_from_env(monkeypatch):
    monkeypatch.setenv("UNSAFE_ALLOW_NO_SANDBOX", "1")
    assert MCPClient._detect_container() is True
    monkeypatch.setenv("UNSAFE_ALLOW_NO_SANDBOX", "0")
    assert MCPClient._detect_container() is False


@pytest.mark.asyncio
async def test_inject_ui_assets_noop_when_not_observable(monkeypatch):
    client = MCPClient(step_delay=0.0)
    call_tool = AsyncMock()
    monkeypatch.setattr(client, "call_tool", call_tool)
    await client.inject_ui_assets()
    call_tool.assert_not_called()


@pytest.mark.asyncio
async def test_inject_ui_assets_calls_evaluate_script(tmp_path: Path, monkeypatch):
    assets_dir = tmp_path / "ui"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "cursor.css").write_text(".cursor { color: red; }", encoding="utf-8")
    (assets_dir / "cursor.js").write_text("window.__cursor = true;", encoding="utf-8")

    client = MCPClient(step_delay=0.1)
    call_tool = AsyncMock(return_value="ok")
    monkeypatch.setattr(client, "call_tool", call_tool)
    monkeypatch.setattr("kubemin_agent.agent.tools.mcp_client.UI_ASSETS_DIR", assets_dir)

    await client.inject_ui_assets()
    call_tool.assert_called_once()
    args, kwargs = call_tool.call_args
    assert args[0] == "evaluate_script"
    assert "window.__cursor = true;" in args[1]["function"]


@pytest.mark.asyncio
async def test_get_element_coordinates_and_animate_cursor(monkeypatch):
    client = MCPClient(step_delay=0.1)
    send_request = AsyncMock(return_value={"content": [{"type": "text", "text": '{"x": 10, "y": 22}'}]})
    monkeypatch.setattr(client, "_send_request", send_request)

    coords = await client.get_element_coordinates("uid-1")
    assert coords == (10, 22)

    await client.animate_cursor(10, 22, is_click=True)
    assert send_request.call_count >= 2


@pytest.mark.asyncio
async def test_get_element_coordinates_handles_bad_payload(monkeypatch):
    client = MCPClient(step_delay=0.1)
    monkeypatch.setattr(client, "_send_request", AsyncMock(return_value={"content": [{"type": "text", "text": "not-json"}]}))
    assert await client.get_element_coordinates("uid-1") is None
    assert await client.get_element_coordinates("") is None


@pytest.mark.asyncio
async def test_send_notification_requires_process():
    client = MCPClient()
    with pytest.raises(RuntimeError, match="not started"):
        await client._send_notification("notifications/initialized", {})


@pytest.mark.asyncio
async def test_send_notification_writes_to_stdin():
    client = MCPClient()
    client._process = MagicMock()
    client._process.stdin = MagicMock()
    client._process.stdin.write = MagicMock()
    client._process.stdin.drain = AsyncMock()
    await client._send_notification("notifications/initialized", {"ok": True})
    client._process.stdin.write.assert_called_once()
    client._process.stdin.drain.assert_awaited_once()


@pytest.mark.asyncio
async def test_read_responses_handles_result_and_error(monkeypatch):
    client = MCPClient()
    process = MagicMock()
    process.stdout = AsyncMock()
    process.stdout.readline = AsyncMock(
        side_effect=[
            b'{"id": 1, "result": {"ok": true}}\n',
            b'{"id": 2, "error": "boom"}\n',
            b'{"method": "notice"}\n',
            b"",
        ]
    )
    client._process = process

    loop = asyncio.get_event_loop()
    fut_ok = loop.create_future()
    fut_err = loop.create_future()
    client._pending[1] = fut_ok
    client._pending[2] = fut_err

    await client._read_responses()
    assert fut_ok.result() == {"ok": True}
    assert isinstance(fut_err.exception(), RuntimeError)


@pytest.mark.asyncio
async def test_read_responses_breaks_on_invalid_json():
    client = MCPClient()
    process = MagicMock()
    process.stdout = AsyncMock()
    process.stdout.readline = AsyncMock(side_effect=[b"invalid-json\n"])
    client._process = process
    await client._read_responses()
