from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from pathlib import Path
from typing import Optional
import os

class KubeMinAgentConfig(BaseSettings):
    """
    KubeMin Agent Configuration.
    Loads from environment variables (prefix KUBEMIN_) and ~/.kubemin-agent/config.env
    """
    
    # KubeMin API Settings
    api_url: str = Field(default="http://localhost:8080/api/v1", alias="KUBEMIN_API_URL")
    api_token: Optional[str] = Field(default=None, alias="KUBEMIN_API_TOKEN") # Or use OAuth flow later
    
    # Budget Settings (Safety Rails)
    budget_max_tool_calls: int = Field(default=6, description="Maximum number of tool calls per run")
    budget_max_log_lines: int = Field(default=200, description="Max log lines to fetch per call")
    budget_prom_window_minutes: int = Field(default=30, description="Default Prometheus query window in minutes")
    
    # Storage
    run_store_dir: Path = Field(default=Path.home() / ".kubemin-agent" / "runs")
    
    # Model Settings (for later)
    model_provider: str = Field(default="openai")
    model_name: str = Field(default="gpt-4-turbo")

    # Chat Agent Settings (nanobot-style generic agent)
    agent_workspace: Path = Field(default=Path.home() / ".kubemin-agent" / "workspace")
    agent_sessions_dir: Path = Field(default=Path.home() / ".kubemin-agent" / "sessions")
    agent_api_base: str = Field(default="https://api.openai.com/v1")
    agent_api_key: Optional[str] = Field(default=None)
    agent_model: str = Field(default="gpt-4o-mini")
    agent_max_iterations: int = Field(default=12)
    agent_history_limit: int = Field(default=30)
    agent_exec_timeout_s: int = Field(default=30)
    agent_restrict_workspace: bool = Field(default=True)
    
    model_config = SettingsConfigDict(
        env_prefix="KUBEMIN_",
        env_file=os.path.expanduser("~/.kubemin-agent/config.env"),
        env_file_encoding='utf-8',
        extra='ignore'
    )

    def init_dirs(self):
        """Ensure necessary directories exist."""
        self.run_store_dir.mkdir(parents=True, exist_ok=True)
        self.agent_workspace.mkdir(parents=True, exist_ok=True)
        self.agent_sessions_dir.mkdir(parents=True, exist_ok=True)

    @property
    def resolved_agent_api_key(self) -> Optional[str]:
        """Resolve chat-agent API key with OPENAI_API_KEY fallback."""
        return self.agent_api_key or os.environ.get("OPENAI_API_KEY")

# Global Config Instance
settings = KubeMinAgentConfig()
settings.init_dirs()
