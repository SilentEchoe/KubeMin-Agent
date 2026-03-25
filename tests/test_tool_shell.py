"""Tests for Shell tool execution."""

from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from kubemin_agent.agent.tools.shell import ShellTool


@pytest.fixture
def tool():
    """Create a shell tool instance."""
    return ShellTool()


class _DummyProcess:
    def __init__(self, stdout: bytes, stderr: bytes, returncode: int) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr

    def kill(self) -> None:
        return None


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
    assert "not in the allowed list" in tool._check_safety("python3 script.py")
    assert "not in the allowed list" in tool._check_safety("pip install pytest")
    assert "not in the allowed list" in tool._check_safety("npm run build")


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
    mock_proc.kill = Mock()
    mock_create_proc.return_value = mock_proc
    mock_wait.side_effect = asyncio.TimeoutError()

    result = await tool.execute(command="echo wait", timeout=2)

    assert "timed out after 2s" in result
    mock_proc.kill.assert_called_once()


@pytest.mark.asyncio
async def test_execute_strict_sandbox_unavailable(
    tmp_path: Path,
    monkeypatch,
):
    """Strict sandbox should fail closed when runtime is not available."""
    monkeypatch.setattr("kubemin_agent.agent.tools.sandbox.shutil.which", lambda _: None)
    tool = ShellTool(
        workspace=tmp_path,
        sandbox_mode="strict",
        sandbox_runtime="bwrap",
    )
    result = await tool.execute(command="ls")
    assert "Sandbox runtime 'bwrap' is not available" in result


@pytest.mark.asyncio
async def test_execute_best_effort_sandbox_fallback(
    tmp_path: Path,
    monkeypatch,
):
    """Best-effort sandbox should fallback to host shell execution."""
    monkeypatch.setattr("kubemin_agent.agent.tools.sandbox.shutil.which", lambda _: None)
    calls: list[tuple[tuple, dict]] = []

    async def _fake_create_subprocess_shell(*args, **kwargs):
        calls.append((args, kwargs))
        return _DummyProcess(stdout=b"ok", stderr=b"", returncode=0)

    monkeypatch.setattr(
        "kubemin_agent.agent.tools.shell.asyncio.create_subprocess_shell",
        _fake_create_subprocess_shell,
    )

    tool = ShellTool(
        workspace=tmp_path,
        sandbox_mode="best_effort",
        sandbox_runtime="bwrap",
    )
    result = await tool.execute(command="ls")
    assert "ok" in result
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_execute_uses_sandbox_runtime(
    tmp_path: Path,
    monkeypatch,
):
    """When sandbox runtime is available, execute should use subprocess_exec."""
    monkeypatch.setattr(
        "kubemin_agent.agent.tools.sandbox.shutil.which",
        lambda _: "/usr/bin/bwrap",
    )
    calls: list[tuple[tuple, dict]] = []

    async def _fake_create_subprocess_exec(*args, **kwargs):
        calls.append((args, kwargs))
        return _DummyProcess(stdout=b"sandboxed", stderr=b"", returncode=0)

    monkeypatch.setattr(
        "kubemin_agent.agent.tools.shell.asyncio.create_subprocess_exec",
        _fake_create_subprocess_exec,
    )

    tool = ShellTool(
        workspace=tmp_path,
        sandbox_mode="strict",
        sandbox_runtime="bwrap",
    )
    result = await tool.execute(command="echo hi")

    assert "sandboxed" in result
    assert len(calls) == 1
    args, _kwargs = calls[0]
    assert args[0] == "/usr/bin/bwrap"


@pytest.mark.asyncio
async def test_execute_workspace_restriction_sets_cwd(tmp_path: Path, monkeypatch):
    """Workspace restriction should execute command with workspace cwd."""
    calls: list[tuple[tuple, dict]] = []

    async def _fake_create_subprocess_shell(*args, **kwargs):
        calls.append((args, kwargs))
        return _DummyProcess(stdout=b"ok", stderr=b"", returncode=0)

    monkeypatch.setattr(
        "kubemin_agent.agent.tools.shell.asyncio.create_subprocess_shell",
        _fake_create_subprocess_shell,
    )

    tool = ShellTool(workspace=tmp_path, restrict_to_workspace=True)
    await tool.execute(command="ls")

    assert len(calls) == 1
    _args, called_kwargs = calls[0]
    assert called_kwargs["cwd"] == str(tmp_path.resolve())
