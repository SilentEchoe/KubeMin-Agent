"""Tests for filesystem tools."""

from pathlib import Path

import pytest

from kubemin_agent.agent.tools.filesystem import ReadFileTool, WriteFileTool


@pytest.fixture
def workspace(tmp_path: Path):
    """Temporary workspace."""
    return tmp_path


@pytest.mark.asyncio
async def test_read_file_tool_success(workspace: Path):
    """Test reading a simple file."""
    test_file = workspace / "test.txt"
    test_file.write_text("Hello, World!")
    
    tool = ReadFileTool(workspace)
    assert tool.name == "read_file"
    
    result = await tool.execute(path="test.txt")
    assert result == "Hello, World!"
    
    # Absolute path
    result_abs = await tool.execute(path=str(test_file))
    assert result_abs == "Hello, World!"


@pytest.mark.asyncio
async def test_read_file_tool_not_found(workspace: Path):
    """Test reading a non-existent file."""
    tool = ReadFileTool(workspace)
    result = await tool.execute(path="missing.txt")
    assert "not found" in result


@pytest.mark.asyncio
async def test_read_file_tool_sensitive(workspace: Path):
    """Test reading sensitive files."""
    tool = ReadFileTool(workspace)
    
    # Path inside workspace but sensitive name
    env_file = workspace / ".env"
    env_file.write_text("SECRET=1")
    
    result = await tool.execute(path=".env")
    assert "access denied" in result


@pytest.mark.asyncio
async def test_read_file_tool_outside_workspace(workspace: Path, tmp_path_factory):
    """Test reading a file outside the workspace."""
    other_dir = tmp_path_factory.mktemp("other")
    other_file = other_dir / "external.txt"
    other_file.write_text("External")
    
    tool = ReadFileTool(workspace)
    result = await tool.execute(path=str(other_file))
    assert "outside workspace" in result


@pytest.mark.asyncio
async def test_read_file_tool_truncated(workspace: Path):
    """Test reading a file that exceeds MAX_READ_LENGTH."""
    tool = ReadFileTool(workspace)
    
    big_file = workspace / "big.txt"
    big_content = "A" * 5000
    big_file.write_text(big_content)
    
    result = await tool.execute(path="big.txt")
    assert len(result) < 5000
    assert "... (truncated" in result


@pytest.mark.asyncio
async def test_write_file_tool_success(workspace: Path):
    """Test writing a file."""
    tool = WriteFileTool(workspace)
    assert tool.name == "write_file"
    
    result = await tool.execute(path="new_dir/test.txt", content="New content")
    assert "Successfully wrote" in result
    
    written_file = workspace / "new_dir" / "test.txt"
    assert written_file.exists()
    assert written_file.read_text() == "New content"


@pytest.mark.asyncio
async def test_write_file_tool_sensitive(workspace: Path):
    """Test writing to a sensitive file."""
    tool = WriteFileTool(workspace)
    
    result = await tool.execute(path=".env", content="HACK")
    assert "cannot write to sensitive file" in result
    
    env_file = workspace / ".env"
    assert not env_file.exists()


@pytest.mark.asyncio
async def test_write_file_tool_outside_workspace(workspace: Path, tmp_path_factory):
    """Test writing outside the workspace."""
    other_dir = tmp_path_factory.mktemp("other")
    target_path = other_dir / "hack.txt"
    
    tool = WriteFileTool(workspace)
    result = await tool.execute(path=str(target_path), content="HACK")
    assert "outside workspace" in result
    assert not target_path.exists()
