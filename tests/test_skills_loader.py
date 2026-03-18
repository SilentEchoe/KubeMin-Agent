"""Tests for SkillsLoader metadata parsing and selection."""

from __future__ import annotations

from pathlib import Path

from kubemin_agent.agent.skills import SkillsLoader


def _write_skill(path: Path, content: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(content, encoding="utf-8")


def test_workspace_skill_overrides_builtin(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write_skill(
        workspace / "skills" / "patrol",
        """---
description: custom patrol
always: false
agents: [patrol]
---

# Custom Patrol
""",
    )

    loader = SkillsLoader(workspace)
    patrol = loader.get_skill("patrol")
    assert patrol is not None
    assert patrol.description == "custom patrol"
    assert patrol.path == workspace / "skills" / "patrol"


def test_parse_frontmatter_metadata_and_selection(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    _write_skill(
        workspace / "skills" / "unit-default",
        """---
description: default for unit agent
always: false
agents:
  - unit_agent
triggers: []
version: "2"
---

# Unit Default
""",
    )
    _write_skill(
        workspace / "skills" / "unit-trigger",
        """---
description: trigger-based unit skill
always: false
agents: [unit_agent]
triggers: [urgent, failover]
---

# Unit Trigger
""",
    )
    _write_skill(
        workspace / "skills" / "global-always",
        """---
description: always-on global skill
always: true
agents: []
---

# Global
""",
    )
    _write_skill(
        workspace / "skills" / "other-agent",
        """---
description: only for another agent
always: false
agents: [another_agent]
triggers: []
---

# Other
""",
    )

    loader = SkillsLoader(workspace)

    default_skill = loader.get_skill("unit-default")
    assert default_skill is not None
    assert default_skill.version == "2"
    assert default_skill.agents == ["unit_agent"]
    assert default_skill.triggers == []

    selected_no_trigger = {s.name for s in loader.get_applicable_skills("unit_agent", "check status")}
    assert "unit-default" in selected_no_trigger
    assert "global-always" in selected_no_trigger
    assert "unit-trigger" not in selected_no_trigger
    assert "other-agent" not in selected_no_trigger

    selected_with_trigger = {
        s.name for s in loader.get_applicable_skills("unit_agent", "urgent production issue")
    }
    assert "unit-trigger" in selected_with_trigger


def test_build_skills_summary_includes_scope_metadata(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write_skill(
        workspace / "skills" / "unit-summary",
        """---
description: summary check
always: false
agents: [unit_agent]
triggers: [incident]
---

# Summary
""",
    )

    summary = SkillsLoader(workspace).build_skills_summary()
    assert "unit-summary" in summary
    assert "agents: unit_agent" in summary
    assert "triggers: incident" in summary
