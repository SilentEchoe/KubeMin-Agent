"""Configuration schema using Pydantic."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class AgentDefaults(BaseModel):
    """Default agent configuration."""

    workspace: str = "~/.kubemin-agent/workspace"
    model: str = "anthropic/claude-sonnet-4-20250514"
    max_tokens: int = 8192
    max_context_tokens: int = 6000
    min_recent_history_messages: int = 4
    task_anchor_max_chars: int = 600
    history_message_max_chars: int = 1200
    memory_backend: str = "file"
    memory_top_k: int = 5
    memory_context_max_chars: int = 1400
    temperature: float = 0.7
    max_tool_iterations: int = 20


class AgentsConfig(BaseModel):
    """Agent configuration."""

    defaults: AgentDefaults = Field(default_factory=AgentDefaults)


class ProviderConfig(BaseModel):
    """LLM provider configuration."""

    api_key: str = ""
    api_base: str | None = None


class ProvidersConfig(BaseModel):
    """Configuration for LLM providers."""

    anthropic: ProviderConfig = Field(default_factory=ProviderConfig)
    openai: ProviderConfig = Field(default_factory=ProviderConfig)
    openrouter: ProviderConfig = Field(default_factory=ProviderConfig)
    groq: ProviderConfig = Field(default_factory=ProviderConfig)
    vllm: ProviderConfig = Field(default_factory=ProviderConfig)
    gemini: ProviderConfig = Field(default_factory=ProviderConfig)


class TelegramConfig(BaseModel):
    """Telegram channel configuration."""

    enabled: bool = False
    token: str = ""
    allow_from: list[str] = Field(default_factory=list)


class FeishuConfig(BaseModel):
    """Feishu (Lark) channel configuration."""

    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""
    verification_token: str = ""
    allow_from: list[str] = Field(default_factory=list)


class ChannelsConfig(BaseModel):
    """Configuration for chat channels."""

    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    feishu: FeishuConfig = Field(default_factory=FeishuConfig)


class GatewayConfig(BaseModel):
    """Gateway/server configuration."""

    host: str = "0.0.0.0"
    port: int = 18790


class WebSearchConfig(BaseModel):
    """Web search tool configuration."""

    api_key: str = ""
    max_results: int = 5


class WebToolsConfig(BaseModel):
    """Web tools configuration."""

    search: WebSearchConfig = Field(default_factory=WebSearchConfig)


class ExecToolConfig(BaseModel):
    """Shell exec tool configuration."""

    timeout: int = 30
    restrict_to_workspace: bool = False
    sandbox_mode: Literal["off", "best_effort", "strict"] = "off"
    sandbox_runtime: Literal["auto", "bwrap"] = "auto"
    sandbox_allow_network: bool = False


class SandboxNetworkConfig(BaseModel):
    """Global sandbox network policy configuration."""

    default_deny: bool = True
    enforce_proxy: bool = True
    proxy_url: str = ""
    allowlist: list[str] = Field(default_factory=list)


class SandboxContainerConfig(BaseModel):
    """Container backend configuration for global sandbox launcher."""

    runtime: Literal["docker", "podman"] = "docker"
    image: str = "kubemin-agent:latest"
    workspace_mount: str = "/data/workspace"
    config_mount: str = "/etc/kubemin/config.json"
    read_only_rootfs: bool = True
    pids_limit: int = 512
    memory_limit: str = "2g"
    cpu_limit: str = "2"


class SandboxK8sConfig(BaseModel):
    """Kubernetes deployment-time sandbox enforcement configuration."""

    runtime_class: str = "gvisor"
    require_runtime_class: bool = True


class SandboxConfig(BaseModel):
    """Global process-level sandbox configuration."""

    mode: Literal["off", "best_effort", "strict"] = "strict"
    backends: list[Literal["container", "bwrap"]] = Field(
        default_factory=lambda: ["container", "bwrap"]
    )
    container: SandboxContainerConfig = Field(default_factory=SandboxContainerConfig)
    network: SandboxNetworkConfig = Field(default_factory=SandboxNetworkConfig)
    k8s: SandboxK8sConfig = Field(default_factory=SandboxK8sConfig)


class ToolsConfig(BaseModel):
    """Tools configuration."""

    web: WebToolsConfig = Field(default_factory=WebToolsConfig)
    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)


class KubeMinConfig(BaseModel):
    """KubeMin platform integration configuration."""

    api_base: str = ""
    token: str = ""
    default_namespace: str = "default"


class ControlConfig(BaseModel):
    """Control plane runtime configuration."""

    enabled: bool = True
    fallback_mode: str = "agent_loop"
    max_parallelism: int = 4
    fail_fast: bool = False
    orchestration_mode: str = "orchestrated"  # "orchestrated" | "intent_dispatch"


class EvaluationConfig(BaseModel):
    """Online execution evaluation configuration."""

    enabled: bool = True
    mode: str = "online"
    warn_threshold: int = 60
    llm_judge_enabled: bool = True
    trace_capture: bool = True
    max_trace_steps: int = 50


class ValidatorConfig(BaseModel):
    """Validator configuration."""

    policy_level: str = "standard"


class PatrolConfig(BaseModel):
    """Patrol agent autonomous scheduling configuration."""

    enabled: bool = False
    schedule: str = "0 9 * * *"
    channel: str = "patrol"
    chat_id: str = "system"
    message: str = (
        "执行每日平台巡检：检查所有节点、Pod、Deployment 状态，"
        "分析 Kubernetes 事件，查询 KubeMin 平台健康状态，"
        "生成巡检报告并写入 workspace。"
    )


class Config(BaseSettings):
    """Root configuration for kubemin-agent."""

    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    kubemin: KubeMinConfig = Field(default_factory=KubeMinConfig)
    control: ControlConfig = Field(default_factory=ControlConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    validator: ValidatorConfig = Field(default_factory=ValidatorConfig)
    patrol: PatrolConfig = Field(default_factory=PatrolConfig)

    @property
    def workspace_path(self) -> Path:
        """Get expanded workspace path."""
        return Path(self.agents.defaults.workspace).expanduser()

    def get_api_key(self) -> str | None:
        """Get API key in priority order: OpenRouter > Anthropic > OpenAI > Gemini > Groq > vLLM."""
        return (
            self.providers.openrouter.api_key
            or self.providers.anthropic.api_key
            or self.providers.openai.api_key
            or self.providers.gemini.api_key
            or self.providers.groq.api_key
            or self.providers.vllm.api_key
            or None
        )

    def get_api_base(self) -> str | None:
        """Get API base URL if using OpenRouter, vLLM, or OpenAI-compatible providers."""
        if self.providers.openrouter.api_key:
            return self.providers.openrouter.api_base or "https://openrouter.ai/api/v1"
        if self.providers.vllm.api_base:
            return self.providers.vllm.api_base
        if self.providers.openai.api_base:
            return self.providers.openai.api_base
        return None

    class Config:
        env_prefix = "KUBEMIN_AGENT_"
        env_nested_delimiter = "__"
