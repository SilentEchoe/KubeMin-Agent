"""Tests for HeartbeatService."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from kubemin_agent.heartbeat.service import HeartbeatService


@pytest.fixture
def workspace(tmp_path: Path):
    """Temporary workspace."""
    return tmp_path


def test_heartbeat_init(workspace):
    """Test service initialization."""
    service = HeartbeatService(workspace, interval_seconds=10)
    assert service.interval == 10
    assert service.workspace == workspace
    assert service.heartbeat_file == workspace / "HEARTBEAT.md"
    assert not service._running


def test_read_heartbeat_missing(workspace):
    """Test reading when heartbeat file is missing."""
    service = HeartbeatService(workspace)
    assert service._read_heartbeat() == ""


def test_read_heartbeat_exists(workspace):
    """Test reading when heartbeat file exists."""
    service = HeartbeatService(workspace)
    
    hb_file = workspace / "HEARTBEAT.md"
    hb_file.write_text("  hello world  \n")
    
    # Should strip whitespace
    assert service._read_heartbeat() == "hello world"


@pytest.mark.asyncio
async def test_heartbeat_run_loop_with_tasks(workspace):
    """Test the run loop executes the callback when tasks are found."""
    service = HeartbeatService(workspace, interval_seconds=1)
    
    hb_file = workspace / "HEARTBEAT.md"
    hb_file.write_text("Task 1: do something")
    
    mock_callback = AsyncMock()
    
    # The loop sleeps FIRST, then checks tasks. So we let it sleep (do nothing) 
    # the first time, and then stop the service on the second sleep.
    call_count = 0
    async def mock_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            service.stop()

    with patch("kubemin_agent.heartbeat.service.asyncio.sleep", side_effect=mock_sleep):
        await service.run(mock_callback)
    
    # Callback should be executed with the file content
    mock_callback.assert_called_once_with("Task 1: do something")
    assert not service._running


@pytest.mark.asyncio
async def test_heartbeat_run_loop_ok(workspace):
    """Test the run loop skips execution when file says OK."""
    service = HeartbeatService(workspace, interval_seconds=1)
    
    hb_file = workspace / "HEARTBEAT.md"
    hb_file.write_text(service.HEARTBEAT_OK)
    
    mock_callback = AsyncMock()
    
    async def mock_sleep(seconds):
        service.stop()
    
    with patch("kubemin_agent.heartbeat.service.asyncio.sleep", side_effect=mock_sleep):
        await service.run(mock_callback)
    
    # Callback shouldn't be executed
    mock_callback.assert_not_called()


@pytest.mark.asyncio
async def test_heartbeat_run_loop_exception(workspace):
    """Test the run loop handles exceptions gracefully."""
    service = HeartbeatService(workspace, interval_seconds=1)
    
    # Force _read_heartbeat to raise an error
    with patch.object(service, "_read_heartbeat", side_effect=Exception("Read error")):
        mock_callback = AsyncMock()
        
        call_count = 0
        async def mock_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                service.stop()
        
        with patch("kubemin_agent.heartbeat.service.asyncio.sleep", side_effect=mock_sleep):
            # This should not raise an exception to the caller
            await service.run(mock_callback)
        
        mock_callback.assert_not_called()
