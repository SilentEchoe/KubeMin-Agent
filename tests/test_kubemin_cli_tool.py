"""Tests for KubeMinCliTool safety and execution."""

from __future__ import annotations

from unittest.mock import ANY, AsyncMock, patch

import pytest

from kubemin_agent.agent.tools.kubemin_cli import KubeMinCliTool


@pytest.fixture
def tool() -> KubeMinCliTool:
    return KubeMinCliTool()


@pytest.fixture
def tool_with_defaults() -> KubeMinCliTool:
    return KubeMinCliTool(api_base="http://kubemin.local:8080", namespace="prod")


class TestKubeMinCliToolProperties:
    """Test basic tool properties."""

    def test_name(self, tool: KubeMinCliTool) -> None:
        assert tool.name == "kubemin_cli"

    def test_description_mentions_readonly(self, tool: KubeMinCliTool) -> None:
        assert "read-only" in tool.description.lower()

    def test_parameters_require_command(self, tool: KubeMinCliTool) -> None:
        params = tool.parameters
        assert "command" in params["properties"]
        assert "command" in params["required"]


class TestKubeMinCliToolSafety:
    """Test read-only safety enforcement."""

    @pytest.mark.asyncio
    async def test_allows_get(self, tool: KubeMinCliTool) -> None:
        result = tool._check_safety("kubemin-cli get apps")
        assert result is None

    @pytest.mark.asyncio
    async def test_allows_list(self, tool: KubeMinCliTool) -> None:
        result = tool._check_safety("kubemin-cli list workflows")
        assert result is None

    @pytest.mark.asyncio
    async def test_allows_describe(self, tool: KubeMinCliTool) -> None:
        result = tool._check_safety("kubemin-cli describe app my-app")
        assert result is None

    @pytest.mark.asyncio
    async def test_allows_health(self, tool: KubeMinCliTool) -> None:
        result = tool._check_safety("kubemin-cli health")
        assert result is None

    @pytest.mark.asyncio
    async def test_allows_status(self, tool: KubeMinCliTool) -> None:
        result = tool._check_safety("kubemin-cli status")
        assert result is None

    @pytest.mark.asyncio
    async def test_allows_version(self, tool: KubeMinCliTool) -> None:
        result = tool._check_safety("kubemin-cli version")
        assert result is None

    @pytest.mark.asyncio
    async def test_blocks_delete(self, tool: KubeMinCliTool) -> None:
        result = tool._check_safety("kubemin-cli delete app my-app")
        assert result is not None
        assert "blocked" in result.lower()

    @pytest.mark.asyncio
    async def test_blocks_apply(self, tool: KubeMinCliTool) -> None:
        result = tool._check_safety("kubemin-cli apply -f config.yaml")
        assert result is not None
        assert "blocked" in result.lower()

    @pytest.mark.asyncio
    async def test_blocks_create(self, tool: KubeMinCliTool) -> None:
        result = tool._check_safety("kubemin-cli create app new-app")
        assert result is not None
        assert "blocked" in result.lower()

    @pytest.mark.asyncio
    async def test_blocks_update(self, tool: KubeMinCliTool) -> None:
        result = tool._check_safety("kubemin-cli update config key=val")
        assert result is not None

    @pytest.mark.asyncio
    async def test_blocks_scale(self, tool: KubeMinCliTool) -> None:
        result = tool._check_safety("kubemin-cli scale app my-app --replicas 5")
        assert result is not None

    @pytest.mark.asyncio
    async def test_blocks_sudo_pattern(self, tool: KubeMinCliTool) -> None:
        result = tool._check_safety("sudo kubemin-cli get apps")
        assert result is not None

    @pytest.mark.asyncio
    async def test_blocks_pipe_to_shell(self, tool: KubeMinCliTool) -> None:
        result = tool._check_safety("kubemin-cli get apps | bash")
        assert result is not None

    @pytest.mark.asyncio
    async def test_blocks_unknown_subcommand(self, tool: KubeMinCliTool) -> None:
        result = tool._check_safety("kubemin-cli hack something")
        assert result is not None
        assert "not in the allowed list" in result.lower()

    @pytest.mark.asyncio
    async def test_blocks_empty_command(self, tool: KubeMinCliTool) -> None:
        result = tool._check_safety("")
        assert result is not None

    @pytest.mark.asyncio
    async def test_blocks_no_subcommand(self, tool: KubeMinCliTool) -> None:
        result = tool._check_safety("kubemin-cli")
        assert result is not None


class TestKubeMinCliToolDefaults:
    """Test default flag injection."""

    def test_injects_api_base(self, tool_with_defaults: KubeMinCliTool) -> None:
        result = tool_with_defaults._inject_defaults("kubemin-cli get apps")
        assert "--api-base" in result
        assert "http://kubemin.local:8080" in result

    def test_injects_namespace(self, tool_with_defaults: KubeMinCliTool) -> None:
        result = tool_with_defaults._inject_defaults("kubemin-cli get apps")
        assert "--namespace" in result
        assert "prod" in result

    def test_does_not_duplicate_api_base(self, tool_with_defaults: KubeMinCliTool) -> None:
        result = tool_with_defaults._inject_defaults(
            "kubemin-cli get apps --api-base http://other"
        )
        assert result.count("--api-base") == 1

    def test_does_not_duplicate_namespace(self, tool_with_defaults: KubeMinCliTool) -> None:
        result = tool_with_defaults._inject_defaults(
            "kubemin-cli get apps --namespace staging"
        )
        assert result.count("--namespace") == 1

    def test_no_injection_without_config(self, tool: KubeMinCliTool) -> None:
        result = tool._inject_defaults("kubemin-cli get apps")
        assert "--api-base" not in result
        assert "--namespace" not in result

    def test_normalize_adds_kubemin_cli_prefix(self, tool: KubeMinCliTool) -> None:
        result = tool._normalize_command("get apps --status failed")
        assert result.startswith("kubemin-cli ")

    def test_normalize_rewrites_kubemin_alias(self, tool: KubeMinCliTool) -> None:
        result = tool._normalize_command("kubemin get apps")
        assert result.startswith("kubemin-cli ")


class TestKubeMinCliToolExecution:
    """Test actual command execution with safety blocking."""

    @pytest.mark.asyncio
    async def test_blocked_command_returns_error(self, tool: KubeMinCliTool) -> None:
        result = await tool.execute(command="kubemin-cli delete app foo")
        assert result.startswith("Error")

    @pytest.mark.asyncio
    async def test_timeout_parameter_clamps(self, tool: KubeMinCliTool) -> None:
        # Should not crash with extreme values
        result = await tool.execute(command="kubemin-cli delete app x", timeout=999)
        assert "Error" in result  # blocked by safety, not timeout

    @pytest.mark.asyncio
    @patch("kubemin_agent.agent.tools.kubemin_cli.asyncio.create_subprocess_shell")
    async def test_execute_enforces_normalized_prefix(
        self,
        mock_create_proc,
        tool: KubeMinCliTool,
    ) -> None:
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (b"ok", b"")
        mock_create_proc.return_value = mock_proc

        result = await tool.execute(command="get apps")

        assert "ok" in result
        mock_create_proc.assert_called_once_with(
            "kubemin-cli get apps",
            stdout=ANY,
            stderr=ANY,
        )
