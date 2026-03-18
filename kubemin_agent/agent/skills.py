"""Skills loader for dynamic skill discovery and loading."""

from pathlib import Path

from loguru import logger


class SkillInfo:
    """Metadata for a discovered skill."""

    def __init__(
        self,
        name: str,
        path: Path,
        description: str = "",
        always: bool = False,
        agents: list[str] | None = None,
        triggers: list[str] | None = None,
        version: str = "1",
    ) -> None:
        self.name = name
        self.path = path
        self.description = description
        self.always = always
        self.agents = agents or []
        self.triggers = triggers or []
        self.version = version

    def load_content(self) -> str:
        """Load the full content of the skill's SKILL.md."""
        skill_file = self.path / "SKILL.md"
        if skill_file.exists():
            return skill_file.read_text(encoding="utf-8")
        return ""

    def applies_to_agent(self, agent_name: str) -> bool:
        """Check if this skill applies to the given agent."""
        if not self.agents:
            return True
        return agent_name in self.agents

    def matches_triggers(self, message: str) -> bool:
        """Check if any trigger keyword appears in the message."""
        if not self.triggers:
            return False
        lower = message.lower()
        return any(trigger.lower() in lower for trigger in self.triggers)


class SkillsLoader:
    """
    Discovers and loads skills from workspace and built-in directories.

    Skills are directories containing a SKILL.md file with YAML frontmatter.
    """

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self._skills: dict[str, SkillInfo] = {}
        self._discover()

    def _discover(self) -> None:
        """Discover available skills from workspace and built-in directories."""
        # Workspace skills (higher priority)
        ws_skills = self.workspace / "skills"
        if ws_skills.exists():
            self._scan_directory(ws_skills)

        # Built-in skills
        builtin = Path(__file__).parent.parent / "skills"
        if builtin.exists():
            self._scan_directory(builtin)

    def _scan_directory(self, directory: Path) -> None:
        """Scan a directory for skill folders containing SKILL.md."""
        for child in directory.iterdir():
            if not child.is_dir():
                continue
            skill_file = child / "SKILL.md"
            if not skill_file.exists():
                continue
            if child.name in self._skills:
                continue  # Workspace skills take priority

            description, always, agents, triggers, version = self._parse_frontmatter(skill_file)
            self._skills[child.name] = SkillInfo(
                name=child.name,
                path=child,
                description=description,
                always=always,
                agents=agents,
                triggers=triggers,
                version=version,
            )
            logger.debug(f"Skill discovered: {child.name}")

    def _parse_frontmatter(self, skill_file: Path) -> tuple[str, bool, list[str], list[str], str]:
        """
        Parse YAML frontmatter from a SKILL.md file.

        Returns:
            Tuple of (description, always_load, agents, triggers, version).
        """
        content = skill_file.read_text(encoding="utf-8")
        if not content.startswith("---"):
            return "", False, [], [], "1"

        parts = content.split("---", 2)
        if len(parts) < 3:
            return "", False, [], [], "1"

        metadata = self._parse_frontmatter_map(parts[1])
        description = str(metadata.get("description", ""))
        always = self._to_bool(metadata.get("always", False))
        agents = self._to_list(metadata.get("agents", []))
        triggers = self._to_list(metadata.get("triggers", []))
        version = str(metadata.get("version", "1"))
        return description, always, agents, triggers, version

    def _parse_frontmatter_map(self, raw: str) -> dict[str, object]:
        """Parse a minimal YAML-like frontmatter map without external dependencies."""
        data: dict[str, object] = {}
        lines = raw.splitlines()
        i = 0

        while i < len(lines):
            line = lines[i].rstrip()
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or ":" not in stripped:
                i += 1
                continue

            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()

            if value == "":
                items: list[str] = []
                j = i + 1
                while j < len(lines):
                    child = lines[j]
                    child_stripped = child.strip()
                    if not child_stripped:
                        j += 1
                        continue
                    if not child.startswith((" ", "\t")) and not child_stripped.startswith("-"):
                        break
                    if child_stripped.startswith("-"):
                        items.append(child_stripped[1:].strip().strip('"\''))
                    else:
                        items.append(child_stripped.strip('"\''))
                    j += 1
                data[key] = items
                i = j
                continue

            if value.startswith("[") and value.endswith("]"):
                inner = value[1:-1].strip()
                if inner:
                    data[key] = [part.strip().strip('"\'') for part in inner.split(",")]
                else:
                    data[key] = []
                i += 1
                continue

            if value.lower() in {"true", "false"}:
                data[key] = value.lower() == "true"
                i += 1
                continue

            data[key] = value.strip('"\'')
            i += 1

        return data

    def _to_bool(self, value: object) -> bool:
        """Normalize a frontmatter value to bool."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() == "true"
        return False

    def _to_list(self, value: object) -> list[str]:
        """Normalize a frontmatter value to list[str]."""
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def get_always_skills(self) -> list[SkillInfo]:
        """Get skills that should always be loaded."""
        return [s for s in self._skills.values() if s.always]

    def load_skills_for_context(self, skills: list[SkillInfo]) -> str:
        """Load full content for a list of skills."""
        parts: list[str] = []
        for skill in skills:
            content = skill.load_content()
            if content:
                parts.append(f"### Skill: {skill.name}\n\n{content}")
        return "\n\n".join(parts)

    def build_skills_summary(self) -> str:
        """Build a summary of available skills for the system prompt."""
        if not self._skills:
            return ""

        lines: list[str] = []
        for skill in sorted(self._skills.values(), key=lambda s: s.name):
            if skill.always:
                continue  # Already loaded in full
            desc = skill.description or "No description"
            agents = ",".join(skill.agents) if skill.agents else "*"
            triggers = ",".join(skill.triggers) if skill.triggers else "-"
            lines.append(
                f"- **{skill.name}**: {desc} "
                f"(agents: {agents}, triggers: {triggers}, path: {skill.path / 'SKILL.md'})"
            )

        return "\n".join(lines) if lines else ""

    def get_applicable_skills(self, agent_name: str, message: str) -> list[SkillInfo]:
        """Select skills applicable to an agent and task message."""
        selected: list[SkillInfo] = []
        for skill in self._skills.values():
            if not skill.applies_to_agent(agent_name):
                continue

            if skill.always:
                selected.append(skill)
                continue

            # Agent-scoped skills without triggers are treated as default skills.
            if skill.agents and not skill.triggers:
                selected.append(skill)
                continue

            if message and skill.matches_triggers(message):
                selected.append(skill)

        return selected

    def get_skill(self, name: str) -> SkillInfo | None:
        """Get a skill by name."""
        return self._skills.get(name)

    @property
    def skill_names(self) -> list[str]:
        """Get list of discovered skill names."""
        return list(self._skills.keys())
