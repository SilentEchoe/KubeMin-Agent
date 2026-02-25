"""Configuration loader for kubemin-agent."""

import json
from pathlib import Path

from loguru import logger

from kubemin_agent.config.schema import Config

DEFAULT_CONFIG_DIR = Path.home() / ".kubemin-agent"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"


def load_config(config_path: Path | None = None) -> Config:
    """
    Load configuration from file and environment variables.

    Priority: environment variables > config file > defaults.

    Args:
        config_path: Optional path to config file. Defaults to ~/.kubemin-agent/config.json.

    Returns:
        Loaded configuration.
    """
    path = config_path or DEFAULT_CONFIG_FILE

    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            config = Config(**data)
            logger.debug(f"Config loaded from {path}")
            return config
        except Exception as e:
            logger.warning(f"Failed to load config from {path}: {e}, using defaults")

    return Config()


def save_default_config(config_path: Path | None = None) -> Path:
    """
    Save default configuration to file.

    Args:
        config_path: Optional path to save config. Defaults to ~/.kubemin-agent/config.json.

    Returns:
        Path where config was saved.
    """
    path = config_path or DEFAULT_CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    config = Config()
    data = config.model_dump(mode="json")
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info(f"Default config saved to {path}")
    return path


def ensure_workspace(config: Config) -> Path:
    """
    Ensure workspace directory exists and return its path.

    Args:
        config: Application configuration.

    Returns:
        Resolved workspace path.
    """
    workspace = config.workspace_path
    workspace.mkdir(parents=True, exist_ok=True)

    # Create standard subdirectories
    (workspace / "memory").mkdir(exist_ok=True)
    (workspace / "skills").mkdir(exist_ok=True)

    return workspace
