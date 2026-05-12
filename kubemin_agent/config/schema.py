"""Configuration schema for the new KubeMin-Agent foundation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class MemoryConfig:
    """Hermes-style multi-tenant memory configuration."""

    enabled: bool = True
    root_dir: str = "~/.kubemin-agent"
    user_max_chars: int = 1375
    agent_memory_max_chars: int = 2200
    warning_ratio: float = 0.8
    session_search_enabled: bool = True
    session_search_top_k: int = 5
    external_provider: str = "none"

    def root_path(self) -> Path:
        """Return expanded memory state root."""
        return Path(self.root_dir).expanduser()


@dataclass(frozen=True)
class Config:
    """Root configuration placeholder for the new project baseline."""

    memory: MemoryConfig = field(default_factory=MemoryConfig)
