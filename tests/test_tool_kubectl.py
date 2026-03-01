"""Tests for Kubectl tool."""

from unittest.mock import ANY, AsyncMock, patch

import pytest

from kubemin_agent.agent.tools.kubectl import KubectlTool


@pytest.fixture
def tool():
    """Create a default kubectl tool."""
    return KubectlTool()


@pytest.fixture
def restricted_tool():
    """Create a kubectl tool scoped to specific namespaces."""
    return KubectlTool(allowed_namespaces=["default", "kube-system"])


@pytest.mark.asyncio
async def test_kubectl_properties(tool):
    """Test basic structure."""
    assert tool.name == "kubectl"
    assert "command" in tool.parameters["required"]
    assert "namespace" in tool.parameters["properties"]


def test_build_command(tool):
    """Test namespace injection logic."""
    assert tool._build_command("get pods", "default") == "kubectl get pods -n default"
    # Should not double inject if already present
    assert tool._build_command("get pods -n kube-system", "default") == "kubectl get pods -n kube-system"


def test_check_safety_allowed(tool):
    """Test allowed commands."""
    assert tool._check_safety("get pods") is None
    assert tool._check_safety("describe node minikube") is None
    assert tool._check_safety("logs pod/test") is None


def test_check_safety_blocked(tool):
    """Test explicitly blocked write commands."""
    assert "write operation and is blocked" in tool._check_safety("apply -f deployment.yaml")
    assert "write operation and is blocked" in tool._check_safety("delete pod foo")
    assert "write operation and is blocked" in tool._check_safety("exec -it foo sh")


def test_check_safety_unknown(tool):
    """Test unknown commands."""
    assert "not recognized as a safe command" in tool._check_safety("unknown stuff")


def test_check_safety_namespaces(restricted_tool):
    """Test namespace restrictions."""
    # Permitted
    assert restricted_tool._check_safety("get pods -n default") is None
    assert restricted_tool._check_safety("get pods --namespace kube-system") is None
    assert restricted_tool._check_safety("get pods -n=default") is None

    # Blocked
    assert "not allowed" in restricted_tool._check_safety("get pods -n production")


def test_filter_secrets():
    """Test secret masking."""
    raw = "data:\n  token: ZXlKaGJHY2lPaUpJVXpJMU5pSXNJblI1Y0NJNklrcFhWQ0o5Cg==\n"
    filtered = KubectlTool._filter_secrets(raw)
    assert "ZXlKa" not in filtered
    assert "[SECRET DATA MASKED]" in filtered


@pytest.mark.asyncio
@patch("kubemin_agent.agent.tools.kubectl.asyncio.create_subprocess_shell")
async def test_execute_success(mock_create_proc, tool):
    """Test executing a valid command."""
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (b"pod1\npod2", b"")
    mock_create_proc.return_value = mock_proc

    result = await tool.execute(command="get pods")
    assert "pod1" in result
    assert "pod2" in result
    mock_create_proc.assert_called_once_with(
        "kubectl get pods",
        stdout=ANY,
        stderr=ANY,
    )


@pytest.mark.asyncio
@patch("kubemin_agent.agent.tools.kubectl.asyncio.wait_for")
@patch("kubemin_agent.agent.tools.kubectl.asyncio.create_subprocess_shell")
async def test_execute_timeout(mock_create_proc, mock_wait, tool):
    """Test execution timeout."""
    import asyncio

    mock_proc = AsyncMock()
    mock_create_proc.return_value = mock_proc
    mock_wait.side_effect = asyncio.TimeoutError()

    result = await tool.execute(command="get pods")
    assert "timed out" in result
    mock_proc.kill.assert_called_once()
