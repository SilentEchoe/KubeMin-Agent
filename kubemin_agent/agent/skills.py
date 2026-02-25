"""Skills loader for dynamic skill discovery and loading."""

from pathlib import Path

from loguru import logger


class SkillInfo:
    """Metadata for a discovered skill."""

    def __init__(self, name: str, path: Path, description: str = "", always: bool = False) -> None:
        self.name = name
        self.path = path
        self.description = description
        self.always = always

    def load_content(self) -> str:
        """Load the full content of the skill's SKILL.md."""
        skill_file = self.path / "SKILL.md"
        if skill_file.exists():
            return skill_file.read_text(encoding="utf-8")
        return ""


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

            description, always = self._parse_frontmatter(skill_file)
            self._skills[child.name] = SkillInfo(
                name=child.name,
                path=child,
                description=description,
                always=always,
            )
            logger.debug(f"Skill discovered: {child.name}")

    def _parse_frontmatter(self, skill_file: Path) -> tuple[str, bool]:
        """
        Parse YAML frontmatter from a SKILL.md file.

        Returns:
            Tuple of (description, always_load).
        """
        content = skill_file.read_text(encoding="utf-8")
        if not content.startswith("---"):
            return "", False

        parts = content.split("---", 2)
        if len(parts) < 3:
            return "", False

        frontmatter = parts[1]
        description = ""
        always = False

        for line in frontmatter.strip().split("\n"):
            line = line.strip()
            if line.startswith("description:"):
                description = line.split(":", 1)[1].strip()
            if line.startswith("always:"):
                always = line.split(":", 1)[1].strip().lower() == "true"

        return description, always

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
        for skill in self._skills.values():
            if skill.always:
                continue  # Already loaded in full
            desc = skill.description or "No description"
            lines.append(f"- **{skill.name}**: {desc} (path: {skill.path / 'SKILL.md'})")

        return "\n".join(lines) if lines else ""

    def get_skill(self, name: str) -> SkillInfo | None:
        """Get a skill by name."""
        return self._skills.get(name)

    @property
    def skill_names(self) -> list[str]:
        """Get list of discovered skill names."""
        return list(self._skills.keys())
