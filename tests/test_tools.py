"""Tests for agent tools: filesystem, shell, kubectl, yaml_validator."""

import asyncio

import pytest

from kubemin_agent.agent.tools.filesystem import ReadFileTool, WriteFileTool
from kubemin_agent.agent.tools.kubectl import KubectlTool
from kubemin_agent.agent.tools.shell import ShellTool
from kubemin_agent.agent.tools.yaml_validator import YAMLValidatorTool


@pytest.fixture
def workspace(tmp_path):
    """Create a temporary workspace directory."""
    return tmp_path


# --- ReadFileTool ---

class TestReadFileTool:
    def test_read_existing_file(self, workspace):
        (workspace / "hello.txt").write_text("Hello, World!")
        tool = ReadFileTool(workspace)
        result = asyncio.get_event_loop().run_until_complete(tool.execute(path="hello.txt"))
        assert result == "Hello, World!"

    def test_read_nonexistent_file(self, workspace):
        tool = ReadFileTool(workspace)
        result = asyncio.get_event_loop().run_until_complete(tool.execute(path="nope.txt"))
        assert "not found" in result

    def test_read_outside_workspace(self, workspace):
        tool = ReadFileTool(workspace)
        result = asyncio.get_event_loop().run_until_complete(tool.execute(path="/etc/passwd"))
        assert "outside workspace" in result

    def test_read_sensitive_file(self, workspace):
        (workspace / ".env").write_text("SECRET=xxx")
        tool = ReadFileTool(workspace)
        result = asyncio.get_event_loop().run_until_complete(tool.execute(path=".env"))
        assert "denied" in result or "sensitive" in result


# --- WriteFileTool ---

class TestWriteFileTool:
    def test_write_new_file(self, workspace):
        tool = WriteFileTool(workspace)
        result = asyncio.get_event_loop().run_until_complete(
            tool.execute(path="output.txt", content="test content")
        )
        assert "Successfully" in result
        assert (workspace / "output.txt").read_text() == "test content"

    def test_write_creates_parent_dirs(self, workspace):
        tool = WriteFileTool(workspace)
        result = asyncio.get_event_loop().run_until_complete(
            tool.execute(path="sub/dir/file.txt", content="nested")
        )
        assert "Successfully" in result
        assert (workspace / "sub" / "dir" / "file.txt").read_text() == "nested"

    def test_write_outside_workspace(self, workspace):
        tool = WriteFileTool(workspace)
        result = asyncio.get_event_loop().run_until_complete(
            tool.execute(path="/tmp/escape.txt", content="bad")
        )
        assert "outside workspace" in result


# --- ShellTool ---

class TestShellTool:
    def test_allowed_command(self):
        tool = ShellTool()
        result = asyncio.get_event_loop().run_until_complete(
            tool.execute(command="echo hello")
        )
        assert "hello" in result

    def test_blocked_command_sudo(self):
        tool = ShellTool()
        result = asyncio.get_event_loop().run_until_complete(
            tool.execute(command="sudo ls")
        )
        assert "blocked" in result.lower() or "not in the allowed" in result.lower()

    def test_blocked_command_rm_rf(self):
        tool = ShellTool()
        result = asyncio.get_event_loop().run_until_complete(
            tool.execute(command="rm -rf /")
        )
        assert "blocked" in result.lower() or "not in the allowed" in result.lower()

    def test_unknown_command_blocked(self):
        tool = ShellTool()
        result = asyncio.get_event_loop().run_until_complete(
            tool.execute(command="dangerous_custom_tool --delete-all")
        )
        assert "not in the allowed" in result


# --- KubectlTool ---

class TestKubectlTool:
    def test_blocked_write_command(self):
        tool = KubectlTool()
        result = asyncio.get_event_loop().run_until_complete(
            tool.execute(command="apply -f deployment.yaml")
        )
        assert "blocked" in result

    def test_blocked_delete_command(self):
        tool = KubectlTool()
        result = asyncio.get_event_loop().run_until_complete(
            tool.execute(command="delete pod my-pod")
        )
        assert "blocked" in result

    def test_unknown_subcommand_blocked(self):
        tool = KubectlTool()
        result = asyncio.get_event_loop().run_until_complete(
            tool.execute(command="exec -it pod -- bash")
        )
        assert "blocked" in result

    def test_namespace_restriction(self):
        tool = KubectlTool(allowed_namespaces=["default", "staging"])
        result = asyncio.get_event_loop().run_until_complete(
            tool.execute(command="get pods -n production")
        )
        assert "not allowed" in result


# --- YAMLValidatorTool ---

class TestYAMLValidatorTool:
    def test_valid_yaml(self):
        tool = YAMLValidatorTool()
        content = """
apiVersion: v1
kind: Service
metadata:
  name: my-app
spec:
  ports:
    - port: 80
"""
        result = asyncio.get_event_loop().run_until_complete(
            tool.execute(content=content)
        )
        assert "VALID" in result

    def test_invalid_syntax(self):
        tool = YAMLValidatorTool()
        result = asyncio.get_event_loop().run_until_complete(
            tool.execute(content="key: [invalid yaml")
        )
        assert "INVALID" in result

    def test_missing_required_fields(self):
        tool = YAMLValidatorTool()
        content = """
metadata:
  name: test
"""
        result = asyncio.get_event_loop().run_until_complete(
            tool.execute(content=content)
        )
        assert "apiVersion" in result
        assert "kind" in result
