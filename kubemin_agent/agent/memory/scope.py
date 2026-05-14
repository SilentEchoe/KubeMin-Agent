"""Memory scope primitives."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kubemin_agent.utils.helpers import sanitize_identifier


@dataclass(frozen=True)
class MemoryScope:
    """
    Multi-tenant memory scope.

    USER.md is scoped by tenant + user.
    Personal MEMORY.md is scoped by tenant + user + agent.
    TEAM.md is scoped by tenant + team.
    Team MEMORY.md is scoped by tenant + team + agent.
    """

    tenant_id: str
    user_id: str
    agent_name: str
    team_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", sanitize_identifier(self.tenant_id))
        object.__setattr__(self, "user_id", sanitize_identifier(self.user_id, default="local"))
        object.__setattr__(self, "agent_name", sanitize_identifier(self.agent_name, default="general"))
        object.__setattr__(self, "team_id", sanitize_identifier(self.team_id, default=""))

    @property
    def has_team(self) -> bool:
        """Return whether this scope includes an explicit team."""
        return bool(self.team_id)

    def user_dir(self, root: Path) -> Path:
        """Return the scoped user directory under the memory root."""
        return root / "memory" / "tenants" / self.tenant_id / "users" / self.user_id

    def agent_dir(self, root: Path) -> Path:
        """Return the scoped agent directory under the memory root."""
        return self.user_dir(root) / "agents" / self.agent_name

    def team_dir(self, root: Path) -> Path:
        """Return the scoped team directory under the memory root."""
        if not self.has_team:
            raise ValueError("team_id is required for team memory")
        return root / "memory" / "tenants" / self.tenant_id / "teams" / self.team_id

    def team_agent_dir(self, root: Path) -> Path:
        """Return the scoped team agent directory under the memory root."""
        return self.team_dir(root) / "agents" / self.agent_name

    def to_metadata(self) -> dict[str, str]:
        """Return serializable scope metadata."""
        return {
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "agent_name": self.agent_name,
            "team_id": self.team_id,
        }
