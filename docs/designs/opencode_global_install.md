# Global OpenCode install for EGM

- **Author:** OpenCode adapter contributors
- **Status:** Proposal. An aligned `design-ready` issue and maintainer scope approval are required before a Stage 1 pull request.
- **Date:** 2026-11-08
- **Tracking:** Refs #146 (OpenCode harness). A dedicated `design-ready` issue is required before a Stage 1 pull request.

## Problem and goals

The OpenCode adapter installs EGM into one project. It copies the bundle under
`<project>/.opencode/egm/bundle`, writes the generated agents under
`<project>/.opencode/agents`, and merges the `skills` array and commands into
`<project>/opencode.json`. Every new project needs another install, and every
install keeps its own copy.

OpenCode also discovers agents, skills, and commands from the global config
directory `~/.config/opencode`. A global install would make EGM available in
every project from one copy, without changing a project's configuration.

Goals:

- Make the `egm` agent, the eight reviewers, the scout, the seven commands, and
  the seven skills available in every OpenCode project.
- Keep the bundle byte-identical to the repository.
- Preserve reviewer isolation and the `.env` read restrictions.
- Keep project installs working and able to override the global copy.
- Keep the install reversible with a documented uninstall.
- Keep the adapter model-agnostic; no model is pinned.

Non-goals:

- A marketplace or plugin-package listing. EGM remains a skills and agents
  bundle, not an OpenCode plugin package.
- Setting a global default agent. That would force EGM on every session.
- Editing canonical skill, persona, or standard text.
- Supporting non-OpenCode harnesses.
- Auto-updating the global bundle from a checkout or release.
- Installing bootstrap by default; bootstrap stays behind
  `--enable-bootstrap`.

## Current behavior

`install_win.py` is project-local. It resolves `ROOT` from the adapter
location, copies `skills/`, `agents/`, `resources/`, and `docs/` into
`<project>/.opencode/egm/bundle`, writes the generated agents to
`<project>/.opencode/agents`, and merges the project `opencode.json`. Prompts,
commands, and the `skills` entry are project-relative. The reviewer
`external_directory` deny is safe because the bundle lives inside the project.

## Proposed layout

```text
~/.config/opencode/
├── opencode.json                 merged: skills entry and seven commands
├── agents/
│   ├── egm.md                    primary orchestrator
│   ├── egm-codebase-details.md   eight reviewers
│   ├── ...
│   ├── egm-zoom-out.md
│   └── egm-goldfish-scout.md     only with --enable-bootstrap
└── egm/
    ├── installation.json         provenance and SHA-256
    └── bundle/                   canonical trees, copied unchanged
        ├── skills/
        ├── agents/
        ├── resources/
        └── docs/
```

## Design decisions

### Config root

Resolve the global root in this order:

1. `XDG_CONFIG_HOME` when set: `$XDG_CONFIG_HOME/opencode`.
2. Otherwise `~/.config/opencode`.

Windows uses the same rule because OpenCode uses it. A future maintainer can
add a host override without changing the layout.

### Bundle and agents

The bundle lives at `<root>/egm/bundle`. Generated agents live at
`<root>/agents`. The installer refuses an existing bundle, as it does today;
reinstall after removing `<root>/egm` and the generated agents.

### Config merge

Merge into `<root>/opencode.json`:

- Append the absolute skills path `<root>/egm/bundle/skills` to the `skills`
  array.
- Add the seven commands, each bound to agent `egm`, with templates that read
  the absolute skill path.
- Do not set `default_agent`.
- Leave every other key untouched.

The installer keeps its current refusal on JSONC files and prints the snippet
to merge manually.

### Absolute paths

Global agents are loaded for every project, so project-relative paths are
invalid. The installer writes the absolute bundle path into:

- the `egm` prompt and dispatch instructions,
- every reviewer persona pointer,
- every command template,
- the `skills` entry.

Paths are stored with forward slashes for stable matching.

### External directory allowance

Reviewers deny `external_directory`. A global bundle is outside the project, so
that deny would block reading the persona and standards. The installer appends
one narrow allow after the deny:

```json
{
  "action": "external_directory",
  "resource": "<root>/egm/bundle/*",
  "effect": "allow"
}
```

The `egm` primary gets the same allow after its `external_directory` ask rule.
All other external paths stay denied or ask, as today.

### No global default agent

The installer does not set `default_agent`. A global default would switch every
session to EGM. The user selects `egm` from the agent picker or passes
`--agent egm` when starting a run. `--set-default` remains project-only and is
rejected with `--global`.

### Precedence and collisions

If a project also installs EGM, both copies define the same agent IDs and skill
IDs. The expected behavior is that the project copy wins, matching OpenCode's
configuration precedence. The implementation must verify this on the pinned
host and document the result. The installer prints a warning when it finds a
project install in the current working directory.

### Write scope

Contract writes (`README.md` and `EGM.md`) are auto-allowed in every project
when bootstrap is enabled. Every other write keeps the `edit: ask` fallback.
This is a broader write scope than a project install and must be stated in the
guide.

### Uninstall

Remove `<root>/egm`, the generated `<root>/agents/egm*.md` files, and the
`skills` and `commands` entries the installer added to
`<root>/opencode.json`. Project installs are unaffected.

## Permissions

| Agent | Rule | Action | Resource | Effect |
| :---- | :--- | :----- | :------- | :----- |
| Reviewer | Baseline | `*` | `*` | `deny` |
| Reviewer | Bundle read | `external_directory` | `<root>/egm/bundle/*` | `allow` |
| Reviewer | Outside project | `external_directory` | `*` | `deny` |
| Scout | Baseline | `*` | `*` | `deny` |
| Scout | Bundle read | `external_directory` | `<root>/egm/bundle/*` | `allow` |
| Scout | Outside project | `external_directory` | `*` | `deny` |
| Primary | Baseline | `*` | `*` | `ask` |
| Primary | Bundle read | `external_directory` | `<root>/egm/bundle/*` | `allow` |
| Primary | Other external | `external_directory` | `*` | `ask` |

The last matching rule wins, so the bundle allow must follow the broad rule.

## Data flow

1. OpenCode starts in any project and loads the global agents, skills, and
   commands.
2. The user selects `egm` and invokes a skill or command.
3. The skill reads the bundle through the absolute path; the narrow
   `external_directory` allow permits it.
4. Reviewers read their persona and standards from the bundle and the target
   files from the project.
5. The primary writes reports and contract files in the project directory.
6. Isolation stays as today: reviewers deny edits, shell, MCP, and external
   paths outside the bundle.

## Compatibility

- Project installs remain supported and are expected to take precedence by ID.
- The V1 adapter and every non-OpenCode harness are unchanged.
- The canonical skill and persona text are not edited.
- The bundle remains portable; only the generated paths differ.

## Security and isolation

- The bundle read allow is narrow and path-specific.
- Reviewers still deny `.env`, `grep`, MCP, edits, shell, and subagents.
- A global `egm` can read any project's files. That is required for drafting and
  review and must be stated in the guide.
- Contract writes are auto-allowed in every project; non-contract writes ask.
- Inherited global or managed rules can override the generated rules. Inspect
  the effective configuration before relying on it.

## Testing and evidence

Offline checks:

- Global layout: bundle, agents, config, and provenance paths.
- Config merge: absolute `skills` entry, seven commands, no `default_agent`.
- Absolute paths in agent prompts and command templates.
- The narrow `external_directory` allow appears after the broad rule.
- `--global` with `--set-default` is rejected.
- A project install still produces its current layout.
- Link integrity and table rendering for this document and the guide.

Live checks, opt-in and recorded separately:

- A fresh home directory with two projects.
- Select `egm` in each project and run a review and a bootstrap.
- Verify bundle reads are allowed and non-bundle external reads are denied.
- Verify a project install overrides the global copy.
- Record installation, workflow, and isolation outcomes separately.

## Risks and mitigations

| Risk | Mitigation |
| :--- | :--------- |
| Global bundle is outside the project, so reviewers cannot read it | Narrow `external_directory` allow for the bundle |
| Project and global copies collide | Verify precedence on the pinned host; warn on install |
| Global write scope surprises users | Document contract auto-allow and `edit: ask` fallback |
| Global default agent forces EGM everywhere | Do not set `default_agent`; reject with `--global` |
| Global config is JSONC | Refuse and print the merge snippet, as today |
| Stale global copy after an upgrade | Document reinstall and refuse existing bundle |
| Inherited rules weaken isolation | Inspect effective config; record isolation as unverified until probed |

## Alternatives considered

- **Symlink the global skills directory to a checkout.** No agent generation,
  no command wiring, and symlinks are unreliable on Windows. Rejected.
- **Copy EGM into every project with a template.** Duplicates the bundle and
  reintroduces the per-project install problem. Rejected.
- **Ship an OpenCode plugin package.** A larger surface with an experimental
  plugin API; not needed for agents, skills, and commands. Deferred.
- **Set a global default agent.** Changes every session; rejected.
- **Keep project-only installs.** Safe but does not meet the goal. Rejected.

## Open questions

- Which copy wins when a project and the global config both define `egm` and
  the reviewer IDs? Verify on the pinned host.
- Does the global `skills` array accept absolute Windows paths without
  normalization issues? Verify.
- Should a global install warn when it finds a project install in the current
  working directory, or only when both are selected? Prefer a warning.
- Should the global installer offer a `--force` reinstall that replaces the
  bundle? Defer until a user needs it.

## Implementation status

A Stage 2 draft exists locally. `install_win.py --global` writes the bundle to
the global config directory, places the generated agents under `agents/`, merges
the absolute `skills` entry and seven commands, appends the narrow bundle read
allow, and rejects `--set-default` with `--global`.

Offline tests pass, and a temp-home check loaded ten EGM agents through
`opencode --standalone debug agents` with the absolute skill and command paths.
A live bundle read also succeeded: the `egm` primary read
`agents/zoom_out.md` from the global bundle and returned its first heading,
confirming the narrow external-directory allowance. Because a fresh temp config
has no provider credentials, that run used a working model as a test-only
override; the adapter still pins no model.

The implementation PR remains gated on an aligned `design-ready` issue, a merged
version of this document, and a `pr-ready` issue.
