# Copyright 2026 Google LLC.
# SPDX-License-Identifier: Apache-2.0

"""Offline checks for the Windows-native OpenCode V2 installer."""

import hashlib
import json
from pathlib import Path
import runpy

import pytest

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = runpy.run_path(str(ROOT / "adapters/opencode/install_win.py"))
REVIEWER_IDS = (
    "egm-codebase-details",
    "egm-comprehension",
    "egm-design",
    "egm-implementation-readiness",
    "egm-inventive-catalyst",
    "egm-structural",
    "egm-style",
    "egm-zoom-out",
)


def test_install_copies_canonical_trees_without_links(tmp_path: Path) -> None:
    project = tmp_path / "project"
    config_path = ADAPTER["install"](project, set_default=True)
    identity = json.loads(
        (project / ".opencode/egm/installation.json").read_text(encoding="utf-8")
    )
    canonical = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))

    assert (identity["name"], identity["version"]) == (
        canonical["name"],
        canonical["version"],
    )
    assert identity["harness"] == "opencode-v2"
    assert identity["symlinks"] is False
    assert identity["source_commit"] != ""
    assert sorted(identity["skills"]) == sorted(
        ADAPTER["canonical_name"](path)
        for path in (ROOT / "skills").glob("*/SKILL.md")
    )

    bundle = project / ".opencode/egm/bundle"
    for directory in ("skills", "agents", "resources", "docs"):
        for source in (ROOT / directory).rglob("*"):
            if source.is_file():
                installed = bundle / directory / source.relative_to(ROOT / directory)
                assert installed.read_bytes() == source.read_bytes()
                key = installed.relative_to(project).as_posix()
                assert identity["sha256"][key] == hashlib.sha256(
                    installed.read_bytes()
                ).hexdigest()

    for path in project.rglob("*"):
        assert not path.is_symlink(), f"unexpected symlink: {path}"
        assert not ADAPTER["is_junction"](path), f"unexpected junction: {path}"

    assert config_path == project / "opencode.json"


def test_generated_agents_use_v2_modes_and_read_only_reviewers(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    ADAPTER["install"](project, set_default=False)
    agents = project / ".opencode/agents"
    assert sorted(path.stem for path in agents.glob("*.md")) == [
        "egm",
        *REVIEWER_IDS,
    ]

    orchestrator = (agents / "egm.md").read_text(encoding="utf-8")
    assert "mode: primary" in orchestrator
    assert orchestrator.count("- action:") == 20
    for reviewer in REVIEWER_IDS:
        assert f'resource: "{reviewer}"' in orchestrator

    for reviewer in REVIEWER_IDS:
        body = (agents / f"{reviewer}.md").read_text(encoding="utf-8")
        assert "mode: subagent" in body
        assert 'action: "edit"' not in body
        assert 'action: "shell"' not in body
        assert 'action: "subagent"' not in body
        assert '    effect: "deny"' in body
        assert 'resource: "grep"' not in body
        assert 'resource: "*"' in body
        assert ".opencode/egm/bundle/agents/" in body


def test_config_is_v2_shaped_and_has_no_legacy_keys(tmp_path: Path) -> None:
    project = tmp_path / "project"
    ADAPTER["install"](project, set_default=True)
    config = json.loads((project / "opencode.json").read_text(encoding="utf-8"))

    assert config["default_agent"] == "egm"
    assert config["skills"] == ["./.opencode/egm/bundle/skills"]
    assert isinstance(config["skills"], list)
    assert sorted(config["commands"]) == [
        "egm-bootstrap",
        "egm-brainstorm",
        "egm-draft",
        "egm-drift-report",
        "egm-resolve",
        "egm-review",
        "egm-review-loop",
    ]
    for name, command in config["commands"].items():
        assert command["agent"] == "egm"
        assert f"skills/{name}/SKILL.md" in command["template"]
    for legacy in ("agent", "command", "autoupdate", "permission", "default_mode"):
        assert legacy not in config
    assert "paths" not in config["skills"]


def test_install_preserves_existing_project_configuration(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    existing = {
        "$schema": "https://opencode.ai/config.json",
        "default_agent": "build",
        "model": "opencode/deepseek-v4.1-flash",
        "commands": {
            "egm-review": {"template": "mine", "agent": "build"},
            "deploy": {"template": "run tests"},
        },
        "skills": ["./team-skills"],
    }
    (project / "opencode.json").write_text(json.dumps(existing), encoding="utf-8")

    ADAPTER["install"](project, set_default=True)
    config = json.loads((project / "opencode.json").read_text(encoding="utf-8"))

    assert config["model"] == existing["model"]
    assert config["default_agent"] == "build"
    assert config["skills"] == ["./team-skills", "./.opencode/egm/bundle/skills"]
    assert config["commands"]["deploy"] == {"template": "run tests"}
    assert config["commands"]["egm-review"] == {"template": "mine", "agent": "build"}
    assert len(config["commands"]) == 8


def test_install_refuses_jsonc_and_existing_bundle(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "opencode.json").write_text(
        '{\n  // comment\n  "model": "x"\n}\n', encoding="utf-8"
    )
    with pytest.raises(ValueError):
        ADAPTER["install"](project, set_default=False)

    (project / "opencode.json").unlink()
    ADAPTER["install"](project, set_default=False)
    with pytest.raises(FileExistsError):
        ADAPTER["install"](project, set_default=False)


def test_bootstrap_flag_adds_read_only_scout_and_narrow_writes(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    ADAPTER["install"](project, set_default=False, enable_bootstrap=True)
    agents = project / ".opencode/agents"

    scout = (agents / "egm-goldfish-scout.md").read_text(encoding="utf-8")
    assert "mode: subagent" in scout
    assert 'action: "edit"' not in scout
    assert 'action: "shell"' not in scout
    assert 'action: "subagent"' not in scout
    assert 'resource: "*.env"' in scout
    assert 'action: "grep"' in scout
    assert '"interface": [], "invariants": [], "side_effects": []' in scout

    orchestrator = (agents / "egm.md").read_text(encoding="utf-8")
    assert 'resource: "egm-goldfish-scout"' in orchestrator
    for resource in ("README.md", "*/README.md", "EGM.md", "*/EGM.md"):
        assert f'resource: "{resource}"' in orchestrator
    assert '  - action: "edit"\n    resource: "*"\n    effect: "ask"' in orchestrator
    assert 'effect: "deny"' in orchestrator
    assert orchestrator.count("- action:") == 26
    assert "## Bootstrap" in orchestrator

    identity = json.loads(
        (project / ".opencode/egm/installation.json").read_text(encoding="utf-8")
    )
    assert identity["bootstrap"] is True
    assert identity["agents"]["egm-goldfish-scout"] == "scout"


def test_bootstrap_is_opt_in(tmp_path: Path) -> None:
    project = tmp_path / "project"
    ADAPTER["install"](project, set_default=False)
    agents = project / ".opencode/agents"

    assert not (agents / "egm-goldfish-scout.md").exists()
    orchestrator = (agents / "egm.md").read_text(encoding="utf-8")
    assert 'resource: "egm-goldfish-scout"' not in orchestrator
    assert 'resource: "*/README.md"' not in orchestrator
    assert "Bootstrap is not supported" in orchestrator

    identity = json.loads(
        (project / ".opencode/egm/installation.json").read_text(encoding="utf-8")
    )
    assert identity["bootstrap"] is False
    assert "egm-goldfish-scout" not in identity["agents"]


def test_bootstrap_cli_flag_wires_through(tmp_path: Path) -> None:
    project = tmp_path / "project"
    assert ADAPTER["main"]([str(project), "--enable-bootstrap"]) == 0
    assert (project / ".opencode/agents/egm-goldfish-scout.md").exists()


def test_adapter_does_not_pin_a_model(tmp_path: Path) -> None:
    project = tmp_path / "project"
    ADAPTER["install"](project, set_default=False, enable_bootstrap=True)
    config = json.loads((project / "opencode.json").read_text(encoding="utf-8"))
    assert "model" not in config
    for agent in (project / ".opencode/agents").glob("*.md"):
        frontmatter = agent.read_text(encoding="utf-8").split("---", 2)[1]
        assert "model:" not in frontmatter, agent.name


def test_global_install_uses_global_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_home = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    project = tmp_path / "ignored-project"

    ADAPTER["install"](
        project, set_default=False, enable_bootstrap=True, global_install=True
    )
    root = config_home / "opencode"
    bundle = root / "egm/bundle"

    assert (bundle / "skills/egm-review/SKILL.md").exists()
    assert (root / "agents/egm.md").exists()
    assert (root / "agents/egm-style.md").exists()
    assert (root / "agents/egm-goldfish-scout.md").exists()
    assert not (project / ".opencode/egm").exists()

    config = json.loads((root / "opencode.json").read_text(encoding="utf-8"))
    absolute = bundle.as_posix()
    assert config["skills"] == [f"{absolute}/skills"]
    assert "default_agent" not in config
    assert sorted(config["commands"]) == [
        "egm-bootstrap",
        "egm-brainstorm",
        "egm-draft",
        "egm-drift-report",
        "egm-resolve",
        "egm-review",
        "egm-review-loop",
    ]
    for command in config["commands"].values():
        assert absolute in command["template"]

    reviewer = (root / "agents/egm-style.md").read_text(encoding="utf-8")
    assert f'resource: "{absolute}/*"' in reviewer
    primary = (root / "agents/egm.md").read_text(encoding="utf-8")
    assert f'resource: "{absolute}/*"' in primary

    identity = json.loads(
        (root / "egm/installation.json").read_text(encoding="utf-8")
    )
    assert identity["harness"] == "opencode-v2-global"
    assert identity["global"] is True

    with pytest.raises(ValueError):
        ADAPTER["install"](project, set_default=True, global_install=True)


def test_global_cli_flag_wires_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_home = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    assert ADAPTER["main"](["--global", "--enable-bootstrap"]) == 0
    root = config_home / "opencode"
    assert (root / "agents/egm.md").exists()
    assert (root / "agents/egm-goldfish-scout.md").exists()
    assert ADAPTER["main"](["--global", "--set-default"]) == 1
