# Copyright 2026 Google LLC.
# SPDX-License-Identifier: Apache-2.0

"""Install an EGM bundle for OpenCode V2 on Windows without symbolic links.

This is a Windows-native alternative to ``install.py``. It differs in four
ways:

* No aliases. OpenCode derives a skill ID from ``<source>/<id>/SKILL.md`` and
  every canonical skill directory is already named ``egm-*``, so the installer
  points ``skills`` at ``bundle/skills`` directly.
* V2 native configuration: ``skills`` array, ``commands``, ``agents``, and an
  ordered ``permissions`` list. No deprecated V1 ``agent``/``command``/
  ``skills.paths``/``permission`` fields.
* Project-local and portable. Everything lives under ``<target>/.opencode`` and
  every generated reference is relative to the project root.
* Merge safe. An existing ``opencode.json`` is extended, never replaced.

The installer copies the canonical resource trees unchanged, so the reviewer
personas, skill bodies, and document standards stay byte-identical to the
repository and are recorded in ``installation.json`` by SHA-256.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
REVIEWERS = (
    "codebase_details",
    "comprehension",
    "design_critic",
    "implementation_readiness",
    "inventive_catalyst",
    "structural",
    "style",
    "zoom_out",
)
COPY_TREES = ("skills", "agents", "resources", "docs")
COPY_FILES = ("plugin.json", "LICENSE", "README.md", "TESTING.md")
BUNDLE_RELATIVE = Path(".opencode") / "egm" / "bundle"
GLOBAL_BUNDLE_RELATIVE = Path("egm") / "bundle"
CANONICAL_NAME = re.compile(r"^name: (egm-[a-z-]+)$", re.MULTILINE)

EGM_COLOR = "#1B6EF3"
REVIEWER_COLOR = "#E86E00"
SCOUT_NAME = "egm-goldfish-scout"


def canonical_name(path: Path) -> str:
    """Read a canonical ``egm-*`` name from a frontmatter block."""
    parts = path.read_text(encoding="utf-8").split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"Missing frontmatter: {path}")
    match = CANONICAL_NAME.search(parts[1])
    if not match:
        raise ValueError(f"Missing canonical name: {path}")
    return match.group(1)


def sha256_of(path: Path) -> str:
    """Return the SHA-256 digest of one file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_junction(path: Path) -> bool:
    """Report whether a path is a Windows directory junction.

    Junctions are reparse points that consume a directory name but are not
    reported by ``Path.is_symlink()``. Detection requires Python 3.12+.
    """
    predicate = getattr(os.path, "isjunction", None)
    return bool(predicate(path)) if predicate else False


def yaml_permissions(rules: list[dict[str, str]]) -> str:
    """Render ordered permission rules as YAML frontmatter lines."""
    lines = ["permissions:"]
    for rule in rules:
        lines.append(f'  - action: "{rule["action"]}"')
        lines.append(f'    resource: "{rule["resource"]}"')
        lines.append(f'    effect: "{rule["effect"]}"')
    return "\n".join(lines)


def global_config_root() -> Path:
    """Return the global OpenCode configuration directory."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "opencode"


def reviewer_agent(
    reviewer: str, bundle: str, *, external_allow: str | None = None
) -> str:
    """Build one read-only Goldfish reviewer agent file."""
    permissions = [
        {"action": "*", "resource": "*", "effect": "deny"},
        {"action": "read", "resource": "*", "effect": "allow"},
        {"action": "read", "resource": "*.env", "effect": "deny"},
        {"action": "read", "resource": "*.env.*", "effect": "deny"},
        {"action": "read", "resource": "*.env.example", "effect": "allow"},
        {"action": "read", "resource": "mcp:*", "effect": "deny"},
        {"action": "glob", "resource": "*", "effect": "allow"},
        {"action": "grep", "resource": "*", "effect": "deny"},
        {"action": "external_directory", "resource": "*", "effect": "deny"},
    ]
    if external_allow:
        permissions.append(
            {"action": "external_directory", "resource": external_allow, "effect": "allow"}
        )
    body = f"""Read the persona file first: {bundle}/agents/{reviewer}.md
Then read the target document and the standards supplied by the caller.

You are a Goldfish reviewer: strictly read-only, no conversation history.
Use only the read and glob tools. Do not edit or write files, do not run shell
commands, do not call MCP tools, and do not delegate to subagents.

Return findings to the caller. Do not write reports. Read prior reports only
when they are explicitly supplied and required by the canonical stage. Report
an inaccessible required file as an incomplete review instead of guessing.
"""
    header = "\n".join(
        [
            "---",
            f'description: "EGM read-only {reviewer} Goldfish reviewer"',
            "mode: subagent",
            f'color: "{REVIEWER_COLOR}"',
            "steps: 20",
            yaml_permissions(permissions),
            "---",
            "",
        ]
    )
    return header + body


def scout_agent(*, external_allow: str | None = None) -> str:
    """Build the read-only Goldfish explorer scout agent file."""
    permissions = [
        {"action": "*", "resource": "*", "effect": "deny"},
        {"action": "read", "resource": "*", "effect": "allow"},
        {"action": "read", "resource": "*.env", "effect": "deny"},
        {"action": "read", "resource": "*.env.*", "effect": "deny"},
        {"action": "read", "resource": "*.env.example", "effect": "allow"},
        {"action": "read", "resource": "mcp:*", "effect": "deny"},
        {"action": "glob", "resource": "*", "effect": "allow"},
        {"action": "grep", "resource": "*", "effect": "deny"},
        {"action": "external_directory", "resource": "*", "effect": "deny"},
    ]
    if external_allow:
        permissions.append(
            {"action": "external_directory", "resource": external_allow, "effect": "allow"}
        )
    body = """You are a read-only codebase explorer scout.

Read the source files in the target directory or chunk named by the caller.
Return one JSON object matching this schema:

{"interface": [], "invariants": [], "side_effects": []}

Rules:

* Cite the exact `[file:symbol_or_flag]` for every entry.
* Never infer RPC methods, routes, status enums, or invariants from file or
  directory names alone.
* Use `["None"]` when the code contains no explicit invariants or side effects.
* Do not write or modify any file, run shell commands, call MCP tools, or
  delegate to subagents.
* Report an unreadable required file as incomplete instead of guessing.
"""
    header = "\n".join(
        [
            "---",
            'description: "EGM read-only codebase explorer scout"',
            "mode: subagent",
            f'color: "{REVIEWER_COLOR}"',
            "steps: 20",
            yaml_permissions(permissions),
            "---",
            "",
        ]
    )
    return header + body


def egm_agent(
    bundle: str,
    *,
    enable_bootstrap: bool = False,
    external_allow: str | None = None,
) -> str:
    """Build the EGM Elephant orchestrator agent file."""
    permissions = [
        {"action": "*", "resource": "*", "effect": "ask"},
        {"action": "read", "resource": "*", "effect": "allow"},
        {"action": "read", "resource": "*.env", "effect": "ask"},
        {"action": "read", "resource": "*.env.*", "effect": "ask"},
        {"action": "read", "resource": "*.env.example", "effect": "allow"},
        {"action": "glob", "resource": "*", "effect": "allow"},
        {"action": "grep", "resource": "*", "effect": "allow"},
        {"action": "question", "resource": "*", "effect": "allow"},
        {"action": "skill", "resource": "*", "effect": "deny"},
        {"action": "skill", "resource": "egm-*", "effect": "allow"},
        {"action": "subagent", "resource": "*", "effect": "deny"},
    ]
    permissions += [
        {"action": "subagent", "resource": name, "effect": "allow"}
        for name in reviewer_names()
    ]
    if enable_bootstrap:
        permissions += [
            {"action": "edit", "resource": "*", "effect": "ask"},
            {"action": "edit", "resource": "README.md", "effect": "allow"},
            {"action": "edit", "resource": "*/README.md", "effect": "allow"},
            {"action": "edit", "resource": "EGM.md", "effect": "allow"},
            {"action": "edit", "resource": "*/EGM.md", "effect": "allow"},
            {"action": "subagent", "resource": SCOUT_NAME, "effect": "allow"},
        ]
    permissions += [
        {"action": "external_directory", "resource": "*", "effect": "ask"},
    ]
    if external_allow:
        permissions.append(
            {"action": "external_directory", "resource": external_allow, "effect": "allow"}
        )
    if enable_bootstrap:
        bootstrap_stop = (
            "Bootstrap runs in this primary context; see the Bootstrap section."
        )
        bootstrap_section = f"""
## Bootstrap

When the user asks to bootstrap, read and follow
{bundle}/skills/egm-bootstrap/SKILL.md with these adapter rules:

* Run discovery, partitioning, and contract writes in this primary context.
* The canonical `goldfish-explorer` scout is installed as `{SCOUT_NAME}`.
* Spawn only `{SCOUT_NAME}` subagents for source reads. Do not spawn partition
  workers.
* Keep at most four scouts running at once.
* Honor the 15-directory safety gate and wait for the answer.
* Write only `README.md` and `EGM.md` contract files. Never edit source code.
* Report an incomplete scout as a placeholder and continue.
"""
    else:
        bootstrap_stop = (
            "Bootstrap is not supported by this adapter, because it installs no "
            "orchestrator or scout agents: stop and tell the user to run "
            "`egm-bootstrap` on a supported harness."
        )
        bootstrap_section = ""
    body = f"""You are the EGM Elephant: you hold the project context and draft the
specification. Goldfish reviewers examine the draft from a fresh context.

EGM bundle root: {bundle}
Resolve agents/, resources/, and docs/ against that root. Resolve references/
against the canonical skill directory. Resolve user files and outputs against
the project working directory.

## Dispatch

Dispatch reviewers with the `subagent` tool:

* Set the agent to the canonical persona name, for example `egm-style`.
* Omit `sessionID` so every review starts a fresh child session. Never resume
  or reuse a reviewer session.
* Run in the foreground and wait for the result.
* Pass absolute paths for the persona, the target document, the standards, and
  the selected reading list.
* Never pass parent history, private reasoning, or memory.

You perform synthesis and you write every report. Reviewers never write.

## Gates

Preserve every readiness, section, and stage approval gate. Wait for the
user's answer. Missing tools and elapsed time do not constitute approval.
When a skill runs brainstorm before draft, complete all seven brainstorm
reviewers and synthesize them into `concepts_brief.md` before drafting. In
review, write each completed stage report before starting the next stage, and
verify `zoom_out_report.md` exists before Step 8.

## Stop conditions

Stop if delegation is unavailable. Never simulate Goldfish reviewers in the
parent conversation: a review in the same context is not a Goldfish review.
Report a missing start, completion, required read, or malformed result as
incomplete.
{bootstrap_stop}
{bootstrap_section}
## Windows notes

Paths are Windows paths; the read tool accepts forward slashes or escaped
backslashes. Never paste untrusted review material into a slash-command
argument, because OpenCode expands `!` shell markers before permissions apply.

`docs/opencode.md` inside the bundle describes the superseded V1 adapter (`task`
tool, `OPENCODE_CONFIG`, `--agent`). Do not follow it. This install is V2:
dispatch with `subagent` and select reviewers by agent ID.
"""
    header = "\n".join(
        [
            "---",
            'description: "EGM Elephant orchestrator: drafts specs, dispatches fresh Goldfish reviewers"',
            "mode: primary",
            f'color: "{EGM_COLOR}"',
            yaml_permissions(permissions),
            "---",
            "",
        ]
    )
    return header + body


def reviewer_names() -> tuple[str, ...]:
    """Return the canonical reviewer agent names in stable order."""
    return tuple(canonical_name(ROOT / "agents" / f"{name}.md") for name in REVIEWERS)


def build_commands(skills: dict[str, Path], bundle: str) -> dict[str, dict[str, str]]:
    """Build one OpenCode command per canonical skill."""
    commands = {}
    for skill_id, skill_md in skills.items():
        commands[skill_id] = {
            "description": f"Run {skill_id} (EGM, OpenCode V2)",
            "agent": "egm",
            "template": (
                f"Read and execute {bundle}/skills/{skill_id}/SKILL.md "
                "against the current project.\n"
                "User request: $ARGUMENTS"
            ),
        }
    return commands


def load_json_config(path: Path) -> dict:
    """Read an existing JSON config, refusing JSONC we cannot merge safely."""
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{path} is not plain JSON (comments or trailing commas). "
            "Merge the printed snippet manually."
        ) from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return loaded


def merge_config(existing: dict, additions: dict, *, set_default: bool) -> tuple[dict, list[str]]:
    """Merge generated settings into an existing configuration."""
    merged = json.loads(json.dumps(existing))
    notes: list[str] = []
    merged.setdefault("$schema", "https://opencode.ai/config.json")

    skills = merged.get("skills", [])
    if isinstance(skills, dict):
        raise ValueError("Existing 'skills' uses the V1 object form; convert it to an array first")
    for entry in additions["skills"]:
        if entry not in skills:
            skills.append(entry)
    merged["skills"] = skills

    commands = merged.get("commands", {})
    if "command" in merged:
        notes.append("Existing V1 'command' map left untouched; new commands use 'commands'")
    for name, definition in additions["commands"].items():
        if name in commands:
            notes.append(f"Command '{name}' already exists; kept the existing definition")
            continue
        commands[name] = definition
    merged["commands"] = commands

    if set_default:
        if "default_agent" in merged and merged["default_agent"] != "egm":
            notes.append(
                f"Kept existing default_agent '{merged['default_agent']}'; "
                "select 'egm' from the agent picker to use EGM"
            )
        else:
            merged["default_agent"] = "egm"
    elif "default_agent" not in merged:
        notes.append("default_agent not set; select 'egm' from the agent picker")

    return merged, notes


def install(
    target: Path,
    *,
    set_default: bool,
    enable_bootstrap: bool = False,
    global_install: bool = False,
) -> Path:
    """Create a symlink-free EGM install, project-local or global."""
    if global_install:
        if set_default:
            raise ValueError(
                "--set-default is project-only; do not set a global default agent"
            )
        target = global_config_root().expanduser().resolve()
        bundle_root = target / GLOBAL_BUNDLE_RELATIVE
        bundle = bundle_root.as_posix()
        skills_entry = f"{bundle}/skills"
        external_allow = f"{bundle}/*"
    else:
        target = target.expanduser().resolve()
        bundle_root = target / BUNDLE_RELATIVE
        bundle = BUNDLE_RELATIVE.as_posix()
        skills_entry = f"./{bundle}/skills"
        external_allow = None
    if bundle_root.exists():
        raise FileExistsError(
            f"{bundle_root} already exists; remove it or reinstall"
        )

    skills = {
        name: path
        for path in sorted((ROOT / "skills").glob("*/SKILL.md"))
        if (name := canonical_name(path))
    }
    additions = {
        "skills": [skills_entry],
        "commands": build_commands(skills, bundle),
    }
    # Validate the target configuration before writing anything, so a refused
    # or malformed config never leaves a half-installed bundle behind.
    config_path = target / "opencode.json"
    merged, notes = merge_config(
        load_json_config(config_path), additions, set_default=set_default
    )

    target.mkdir(parents=True, exist_ok=True)
    bundle_root.mkdir(parents=True)
    for tree in COPY_TREES:
        shutil.copytree(ROOT / tree, bundle_root / tree)
    for filename in COPY_FILES:
        shutil.copy2(ROOT / filename, bundle_root / filename)

    agents_dir = target / "agents" if global_install else target / ".opencode" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    reviewers = reviewer_names()
    written: dict[str, str] = {}
    for reviewer, name in zip(REVIEWERS, reviewers):
        (agents_dir / f"{name}.md").write_text(
            reviewer_agent(reviewer, bundle, external_allow=external_allow),
            encoding="utf-8",
        )
        written[name] = "reviewer"
    (agents_dir / "egm.md").write_text(
        egm_agent(
            bundle,
            enable_bootstrap=enable_bootstrap,
            external_allow=external_allow,
        ),
        encoding="utf-8",
    )
    written["egm"] = "primary"
    if enable_bootstrap:
        (agents_dir / f"{SCOUT_NAME}.md").write_text(
            scout_agent(external_allow=external_allow), encoding="utf-8"
        )
        written[SCOUT_NAME] = "scout"

    config_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")

    provenance = {
        "name": "egm",
        "version": json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))["version"],
        "harness": "opencode-v2-global" if global_install else "opencode-v2",
        "global": global_install,
        "adapter": "adapters/opencode/install_win.py",
        "status": "experimental",
        "symlinks": False,
        "bootstrap": enable_bootstrap,
        "source_commit": git_commit(ROOT),
        "agents": written,
        "skills": sorted(skills),
        "sha256": {
            path.relative_to(target).as_posix(): sha256_of(path)
            for path in sorted(bundle_root.rglob("*"))
            if path.is_file()
        },
    }
    (bundle_root.parent / "installation.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Installed EGM into {target}")
    print(f"  bundle:  {bundle_root}")
    print(f"  agents:  {agents_dir} ({len(written)})")
    print(f"  skills:  {len(skills)} via {additions['skills'][0]}")
    print(f"  config:  {config_path}")
    if enable_bootstrap:
        print("  bootstrap: enabled (read-only scout, narrow contract writes)")
    for note in notes:
        print(f"  note:    {note}")
    print("\nVerify (from any project):" if global_install else "\nVerify (from the project root):")
    print("  opencode debug config")
    print("  opencode debug agents")
    print("\nThen select the 'egm' agent and use an ordinary message, for example:")
    print("  Use the egm-review skill to review docs/my-design.md")
    return config_path


def git_commit(root: Path) -> str:
    """Return the checked-out commit when the tree is a Git checkout."""
    git = root / ".git"
    if not git.is_dir():
        return "unknown"
    try:
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    if not head.startswith("ref: "):
        return head
    ref = head[5:].strip()
    loose = git / ref
    if loose.exists():
        return loose.read_text(encoding="utf-8").strip()
    packed = git / "packed-refs"
    if packed.exists():
        for line in packed.read_text(encoding="utf-8").splitlines():
            if line.endswith(f" {ref}"):
                return line.split(" ", 1)[0].strip()
    return "unknown"


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and install."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "target",
        nargs="?",
        type=Path,
        default=Path.cwd(),
        help="Project to enable EGM in (default: current directory)",
    )
    parser.add_argument(
        "--set-default",
        action="store_true",
        help="Set default_agent to egm when the project has no different default",
    )
    parser.add_argument(
        "--enable-bootstrap",
        action="store_true",
        help=(
            "Add the read-only explorer scout and narrow README.md/EGM.md "
            "writes for egm-bootstrap"
        ),
    )
    parser.add_argument(
        "--global",
        dest="global_install",
        action="store_true",
        help="Install into the global OpenCode config directory for every project",
    )
    args = parser.parse_args(argv)
    try:
        install(
            args.target,
            set_default=args.set_default,
            enable_bootstrap=args.enable_bootstrap,
            global_install=args.global_install,
        )
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
