<!-- Copyright 2026 Google LLC. SPDX-License-Identifier: Apache-2.0 -->

# OpenCode V2 on Windows

`install_win.py` is a Windows-native alternative to `install.py`. It targets
OpenCode **V2** configuration and creates no symbolic links or junctions.

## Why a second installer

`install.py` targets OpenCode V1 `1.18.29` and has three Windows problems:

1. It creates seven directory symlinks for the skill aliases. Symlinks need
   Developer Mode or elevation, and any consumer that checks only
   `is_symlink()` treats a junction as an ordinary directory.
2. It emits V1 configuration (`agent`, `command`, `skills.paths`, `permission`,
   `autoupdate`). V2 normalizes these, but every nested agent entry has to stay
   in one format and the result carries deprecation noise.
3. It expects the POSIX launch `OPENCODE_CONFIG=... opencode --agent egm`. V2
   has no `--agent` flag.

The symlink step is not needed at all. OpenCode derives a skill ID from
`<source>/<id>/SKILL.md`, and all seven canonical skill directories are already
named `egm-*`, so `skills` can point straight at `bundle/skills`.

## Install

Python 3.10 or newer. No third-party packages.

```powershell
python adapters\opencode\install_win.py <project-dir>
```

Add `--set-default` to make `egm` the project's default agent. Without it the
existing default is preserved and you select `egm` from the agent picker.

Add `--enable-bootstrap` to install the read-only `egm-goldfish-scout` subagent
and a narrow `README.md` / `EGM.md` write envelope for `egm-bootstrap`. Without
the flag, bootstrap stops with an explicit message and the install is unchanged.

Re-running against the same project stops at the existing bundle. Remove
`<project-dir>\.opencode\egm` to reinstall; generated agent files are then
rewritten on the next run.

## Global install

Install once for every project:

```powershell
python adapters\opencode\install_win.py --global --enable-bootstrap
```

This writes the bundle to `~/.config/opencode/egm/bundle`, the agents to
`~/.config/opencode/agents`, and merges the `skills` array and seven commands
into `~/.config/opencode/opencode.json`. It honors `XDG_CONFIG_HOME` when set.
It does not set `default_agent`; select `egm` per session. `--set-default` is
project-only and is rejected with `--global`.

A global bundle is outside the project, so the generated reviewers and scout
allow reads under `~/.config/opencode/egm/bundle/*` before their
`external_directory` deny. Every other external path stays denied. The primary
agent gets the same narrow allow; other external paths stay `ask`.

Contract writes (`README.md`/`EGM.md`) are auto-allowed in every project; other
writes keep the `edit: ask` fallback. Uninstall removes `~/.config/opencode/egm`,
the generated `egm*.md` agents, and the added `skills`/`commands` entries.

## Layout

```text
<project>/
├── opencode.json                     merged, never replaced
└── .opencode/
    ├── agents/                       9 or 10 native V2 agents
    │   ├── egm.md                    primary, orchestrator
    │   ├── egm-codebase-details.md   subagent, read-only
    │   ├── egm-comprehension.md
    │   ├── egm-design.md
    │   ├── egm-implementation-readiness.md
    │   ├── egm-inventive-catalyst.md
    │   ├── egm-structural.md
    │   ├── egm-style.md
    │   ├── egm-zoom-out.md
    │   └── egm-goldfish-scout.md     with --enable-bootstrap
    └── egm/
        ├── installation.json         SHA-256 of every bundled file
        └── bundle/                   canonical trees, copied unchanged
            ├── skills/              7 skills, IDs match directory names
            ├── agents/              8 Goldfish personas
            ├── resources/           document standards
            └── docs/
```

The persona files, skill bodies, and standards are byte-identical to the
repository. The generated agent files only add V2 frontmatter and a pointer to
the canonical persona, so upstream edits stay authoritative.

## Verify

Run from the project root, because generated references are project-relative.

```powershell
opencode debug config
opencode debug agents
```

`debug agents` should list `egm` as `primary` and the eight `egm-*` reviewers as
`subagent`. With `--enable-bootstrap`, `egm-goldfish-scout` also appears as a
`subagent`. `debug config` should show the project `opencode.json` with a
`skills` array and seven `commands` entries.

Then select `egm` and use an ordinary message:

```text
Use the egm-review skill to review docs/my-design.md
```

## Reviewers

All eight canonical reviewer personas are installed as generated V2 subagents.
`brainstorm` needs all seven lenses, including `egm-inventive-catalyst`, and
`review` Step 5 (Initial Zoom Out) pairs `egm-zoom-out` with
`egm-inventive-catalyst`, so every canonical stage has its persona available.

Each reviewer is denied everything, then allowed `read` and `glob`. `grep` is
denied because grep searches bypass per-file `read` rules and could expose
`.env` files. `mcp:*` reads are denied for the same reason. `external_directory`
is denied, so reviewers only see files inside the project; the bundle is inside
the project by design.

The orchestrator is denied `skill` and `subagent` by default and allows only
`egm-*` skills and the eight reviewer IDs, so it cannot reach unrelated agents
or skills.

With `--enable-bootstrap`, `egm-goldfish-scout` runs the source scan using the
same read-only envelope as a reviewer and returns JSON instead of review text.
The primary `egm` agent performs discovery and writes `README.md` and `EGM.md`
contract files without a prompt. Other EGM artifacts (`concepts_brief.md`,
`design_draft.md`, and review reports) keep the `ask` fallback so the other
skills still work.

## Known limits

* **V2 interface changes.** This adapter targets V2 `subagent` and
  `permissions`. Agent `request` overlays are accepted by the schema but are not
  sent with model requests in V2; none are generated.
* **No model pin.** The adapter sets no model on the primary, reviewers, or
  scout. Every run uses the OpenCode session/default model; select it in
  OpenCode as usual.
* **The safety gate waits.** A session with no attached client leaves the
  bootstrap approval form pending; it does not auto-answer. Answer it in the TUI,
  the web UI, or through the session form API. Selecting "No" aborts with zero
  contract writes.
* **Shell-marker expansion.** OpenCode expands `!`-backtick shell markers in
  slash-command arguments before tool permissions apply. Never paste untrusted
  review material into a command argument. Markdown fences do not prevent it.
* **Project-relative references.** The `skills` entry and command templates are
  relative to the project root. Start OpenCode from the project root, or convert
  the two references to absolute paths.
* **Isolation is not proven.** A fresh child session is not a security boundary.
  V2 allows `external_directory` access by default; reviewers here deny it, but
  an inherited global or managed configuration can override the generated rules.
  Inspect the effective configuration before relying on it.
* **External targets.** Reviewing a document outside the project needs an
  `external_directory` allow rule, added deliberately and narrowly.
* **Bootstrap is opt-in and bounded.** `--enable-bootstrap` adds the read-only
  scout, automatic contract writes, and an `ask` fallback for other artifacts.
  The primary runs discovery and writing itself, caps concurrent scouts at four,
  and honors the 15-directory safety gate. This deliberately diverges from the
  skill's unbounded worker swarm; true partition workers would need
  `experimental.subagent_depth: 2`.
* **Live workflows verified.** On OpenCode 2.2.6, a 3-directory fixture produced
  four contracts with source byte-identical. A 17-directory fixture paused at the
  safety gate with zero writes, then wrote 18 contracts after a structured
  question-form approval, using 16 `egm-goldfish-scout` sessions in four waves of
  four and no partition workers. A probe child was denied `.env` and external
  reads, exposed no write, shell, or MCP tools, and reported no parent-context
  marker. Brainstorm, draft, and review also completed: 7 brainstorm lenses
  produced `concepts_brief.md`; draft produced `design_draft.md`; review produced
  five stage reports and a consolidated report from 8 reviewers, 7 dispatched in
  one parallel wave. No source files were modified. The parallel-wave driver is
  an opt-in review variant; the canonical sequential preset remains the default.

## Uninstall

Remove `.opencode/egm`, the generated `.opencode/agents/egm*.md` files (nine, or
ten with `--enable-bootstrap`), and the `skills` and `commands` entries the
installer added to `opencode.json`.
