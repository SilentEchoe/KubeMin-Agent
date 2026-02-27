"""Tests for Shell tool execution."""

from unittest.mock import AsyncMock, patch

import pytest

from kubemin_agent.agent.tools.shell import ShellTool


@pytest.fixture
def tool():
    """Create a shell tool instance."""
    return ShellTool()


@pytest.mark.asyncio
async def test_shell_tool_properties(tool):
    """Test basic structure."""
    assert tool.name == "run_command"
    assert "command" in tool.parameters["required"]
    assert "timeout" in tool.parameters["properties"]


def test_check_safety_valid(tool):
    """Test safe commands pass the safety check."""
    assert tool._check_safety("ls -la") is None
    assert tool._check_safety("cat /etc/hosts") is None
    assert tool._check_safety("pip install pytest") is None
    assert tool._check_safety("echo 'hello'") is None
    assert tool._check_safety("git clone https://x") is None


def test_check_safety_blocked_patterns(tool):
    """Test explicitly blocked dangerous patterns."""
    assert "blocked" in tool._check_safety("rm -rf /")
    assert "blocked" in tool._check_safety("sudo rm file")
    assert "blocked" in tool._check_safety("chmod 777 file")
    assert "blocked" in tool._check_safety("kill -9 1234")
    assert "blocked" in tool._check_safety("cat x | bash")
    assert "blocked" in tool._check_safety("ls; sh")


def test_check_safety_unknown_commands(tool):
    """Test commands not in the allowlist are blocked."""
    assert "not in the allowed list" in tool._check_safety("nmap 127.0.0.1")
    assert "not in the allowed list" in tool._check_safety("terraform apply")
    assert "not in the allowed list" in tool._check_safety("docker run")


def test_check_safety_malformed(tool):
    """Test empty or weirdly formatted commands."""
    assert "empty command" in tool._check_safety("   ")
    

@pytest.mark.asyncio
async def test_execute_safety_first(tool):
    """Test execute stops before subprocess if command is unsafe."""
    # We shouldn't need mock because the subprocess is never hit
    result = await tool.execute(command="sudo cat secret")
    assert "blocked" in result


@pytest.mark.asyncio
@patch("kubemin_agent.agent.tools.shell.asyncio.create_subprocess_shell")
async def test_execute_success(mock_create_proc, tool):
    """Test successful command execution."""
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    # stdout, stderr returned by communicate() bytes
    mock_proc.communicate.return_value = (b"file1\nfile2", b"")
    mock_create_proc.return_value = mock_proc
    
    result = await tool.execute(command="ls")
    
    assert "file1" in result
    assert "file2" in result
    assert "[exit_code: 0]" in result
    mock_create_proc.assert_called_once()


@pytest.mark.asyncio
@patch("kubemin_agent.agent.tools.shell.asyncio.create_subprocess_shell")
async def test_execute_with_stderr(mock_create_proc, tool):
    """Test successful execution but command generated stderr output."""
    mock_proc = AsyncMock()
    mock_proc.returncode = 1
    mock_proc.communicate.return_value = (b"", b"no such file or directory")
    mock_create_proc.return_value = mock_proc
    
    result = await tool.execute(command="cat missing")
    
    assert "[stderr]" in result
    assert "no such file or directory" in result
    assert "[exit_code: 1]" in result


@pytest.mark.asyncio
@patch("kubemin_agent.agent.tools.shell.asyncio.wait_for")
@patch("kubemin_agent.agent.tools.shell.asyncio.create_subprocess_shell")
async def test_execute_timeout(mock_create_proc, mock_wait, tool):
    """Test execution catching a timeout."""
    import asyncio
    
    mock_proc = AsyncMock()
    mock_create_proc.return_value = mock_proc
    mock_wait.side_effect = asyncio.TimeoutError()
    
    result = await tool.execute(command="echo wait", timeout=2)
    
    assert "timed out after 2s" in result
    mock_proc.kill.assert_called_once()
