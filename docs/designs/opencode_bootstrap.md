# OpenCode V2 bootstrap support

- **Author:** OpenCode adapter contributors
- **Status:** Proposal. An aligned `design-ready` issue and maintainer scope approval are required before a Stage 1 pull request.
- **Date:** 2026-11-08
- **Tracking:** Refs #146 (OpenCode harness). A dedicated `design-ready` issue is required before a Stage 1 pull request.

## Problem and goals

[`egm-bootstrap`](../../skills/egm-bootstrap/SKILL.md) creates or corrects
EGM-compliant `README.md` files across a directory tree. It discovers the tree
incrementally, partitions large trees, reads source files through read-only
scouts, rolls child contracts into parent blueprints, and preserves a human
safety gate when the tree is large.

The OpenCode V2 adapter
([`install_win.py`](../../adapters/opencode/install_win.py)) installs the `egm`
orchestrator and eight read-only reviewers, then stops bootstrap with an
explicit message. The adapter never installs the bootstrap orchestrator, the
read-only scout, or the write and shell profile the workflow needs. The current
behavior is safe but incomplete.

Goals:

- Run `egm-bootstrap` on OpenCode V2 with the canonical artifacts and gates.
- Keep every scout in a fresh context with enforceable read-only access.
- Restrict writes to the configured contract filenames.
- Keep the change project-local, opt-in, and reversible.
- Leave every non-bootstrap EGM skill unchanged.
- Record installation, workflow, and isolation outcomes separately.

Non-goals:

- Editing canonical skill or persona text.
- Supporting bootstrap on the OpenCode V1 adapter.
- Changing other harnesses.
- Claiming OpenCode support before live evidence exists.
- Unbounded model spend or unbounded parallel spawning.
- A generic OpenCode plugin framework.

## Why it fails today

| Constraint | OpenCode V2 behavior | Effect on bootstrap |
| :--------- | :------------------- | :------------------ |
| Delegation depth | `experimental.subagent_depth` defaults to `1`, so a subagent cannot launch subagents. | The canonical root-to-worker-to-scout tree needs depth 2. |
| Scout persona | V2 has no built-in `scout` agent, and the adapter installs only reviewers. | No read-only `goldfish-explorer` exists to call. |
| Write profile | The adapter grants `edit` only through the broad `ask` fallback. | Writing many contract files would prompt on every file. |
| Discovery profile | Reviewers deny `shell`; the orchestrator asks for it. | BFS discovery and optional formatters have no dedicated profile. |
| Agent registration | The adapter writes static agent files. | The skill asks for a runtime-registered scout with fixed capabilities. |
| Cost control | The skill permits unbounded parallel workers. | The adapter uses foreground, allowlisted subagents and cannot bound spend. |

The adapter also documents this as out of scope. The
[V1 guide](../opencode.md) says to stop when bootstrap needs an orchestrator or
scout, and the
[additional harnesses design](additional-harnesses.md) targets OpenCode V1 and
excludes the V2 interfaces. The V2 Windows installer is a later extension with
no bootstrap design yet.

## Options considered

### A1. Flattened scouts (recommended)

The primary `egm` agent performs discovery, partition planning, and report
writing itself. It spawns only read-only `egm-goldfish-scout` subagents, one per
directory or source chunk, and asks each for the structured JSON contract.

- Delegation depth stays at the default of 1: `egm` to scout.
- No change to `experimental.subagent_depth`.
- Fresh-context reads are preserved.
- The partition-worker layer is collapsed into the primary context.
- Parent roll-ups use the JSON summaries, not raw source.

This is the smallest change that restores the core guarantee: source is read by
isolated, read-only scouts. It is closest to the skill's small-tree path, and it
scales to the 15-directory safety threshold without new configuration.

### A2. Full worker tree with depth 2

Keep the canonical root-to-worker-to-scout structure. Add both a bootstrap
orchestrator subagent and a scout subagent, then set
`experimental.subagent_depth` to `2` in the project configuration.

- Highest fidelity to the canonical workflow.
- Depends on an experimental host setting that lets any subagent launch
  subagents, not only EGM agents.
- Adds a second generated agent and more failure modes.
- Should be a follow-up only if A1 proves too slow or context-heavy.

### B. SDK or plugin orchestrator

OpenCode exposes a server API and SDK that can create sessions with
`agent`, `parentID`, and a per-session `permissions` ruleset, then prompt and
wait on each session. A local plugin could therefore orchestrate workers and
scouts as top-level sessions, bypassing the subagent depth limit.

- Strongest long-term option if depth 1 cannot meet the workflow.
- New distribution surface, experimental plugin API, more code, and its own
  security review.
- Deferred until A1 demonstrates a concrete need.

### C. Inline single-agent bootstrap

Run the scout steps inline in one context. The skill allows this only when a
harness has no subagent tool. OpenCode does have one, and inline reads remove
the fresh-context guarantee while growing the primary context with source code.
Rejected.

### Comparison

| Option | Fresh-context scouts | Depth change | Effort | Main risk |
| :----- | :------------------- | :----------- | :----- | :-------- |
| A1 flattened | Yes | No | Medium | Primary context grows with summaries |
| A2 worker tree | Yes | Yes, to 2 | High | Experimental global delegation setting |
| B SDK plugin | Yes | No | High | Experimental plugin surface |
| C inline | No | No | Low | Loses the Goldfish guarantee |

## Proposed design (A1)

### Generated agents

`install_win.py` gains one new generated agent:

- `egm-goldfish-scout.md` with `mode: subagent`, read-only permissions, and a
  pointer to the canonical persona or an inline scout prompt.

No bootstrap orchestrator agent is generated in A1. The primary `egm` agent
runs the root orchestration and writes the contract files.

### Permissions

The scout mirrors the reviewer envelope so that `.env` and MCP reads stay
closed:

| Rule | Action | Resource | Effect |
| :--- | :----- | :------- | :----- |
| Baseline | `*` | `*` | `deny` |
| Read | `read` | `*` | `allow` |
| Env deny | `read` | `*.env` | `deny` |
| Env deny | `read` | `*.env.*` | `deny` |
| Env example | `read` | `*.env.example` | `allow` |
| Glob | `glob` | `*` | `allow` |
| Search policy | `grep` | `*` | `deny` |
| Outside project | `external_directory` | `*` | `deny` |

The primary `egm` agent gains a narrow write envelope for contract files. Broad
rules come first because the last matching rule wins:

| Rule | Action | Resource | Effect |
| :--- | :----- | :------- | :----- |
| Baseline edit | `edit` | `*` | `ask` |
| Root README | `edit` | `README.md` | `allow` |
| Nested README | `edit` | `*/README.md` | `allow` |
| Root blueprint | `edit` | `EGM.md` | `allow` |
| Nested blueprint | `edit` | `*/EGM.md` | `allow` |

The same primary agent runs every EGM skill, so the baseline stays at `ask`
rather than `deny`. A blanket `deny` blocks `concepts_brief.md`,
`design_draft.md`, and the review reports. Contract files are the only writes
that skip the prompt; every other artifact keeps the inherited approval path.

The exact glob syntax must be validated against the host matcher during
implementation. If the matcher cannot express nested contract paths narrowly,
keep `edit` at `ask` and require an interactive session instead of widening it.

The primary also gains an explicit `subagent` allow for `egm-goldfish-scout` and
keeps `question` for the safety gate. `shell` stays at `ask`.

### Flow

1. The primary confirms the target path and contract filename.
2. It discovers the tree level by level without recursive listing.
3. If more than 15 directories are found, it asks for approval before reading.
4. It walks directories in post-order, deepest first.
5. For each directory or source chunk, it spawns one `egm-goldfish-scout` with
   the directory path, the chunk boundaries, and the child summaries needed for
   parent roll-ups.
6. It collects the scout JSON, merges any existing contract text, and writes the
   contract file with the narrow `edit` envelope.
7. It compiles the root blueprint and reports incomplete scouts as placeholders.
8. It never commits, never edits source, and never simulates a missing scout.

### Fresh context and isolation

Each scout starts in a child session with no parent history. It receives only
absolute paths, chunk boundaries, and interface summaries. It returns JSON and
does not write. A scout that cannot read a required file returns an incomplete
result instead of guessing.

A fresh session alone is not a security boundary. The effective configuration
must be inspected before a run, and inherited global or managed rules can
override the generated envelope. Record isolation as unverified until a live
probe shows enforced denial.

### Safety and cost controls

The canonical skill allows unbounded parallel workers. A1 deliberately bounds
spawning to protect cost and context:

- Default concurrency: four scouts.
- Hard stop at the 15-directory gate until the user approves.
- One retry per failed scout, then a placeholder and a recorded warning.
- No background subagents in the first implementation; add them only after
  foreground behavior is verified.

This is a documented divergence from the canonical "unbounded" wording and
must be called out in the adapter guide.

### Failure handling

| Failure | Required behavior |
| :------ | :---------------- |
| Scout timeout or error | Retry once, then placeholder and continue |
| Required read denied | Report incomplete, never fabricate |
| Write denied | Stop the directory, report the path, keep prior artifacts |
| Approval gate not answered | Wait; elapsed time is not approval |
| User rejects the large-tree gate | Stop without writing |

## Configuration

A1 needs no new configuration key. The installer adds the scout agent and the
narrow permissions only when `--enable-bootstrap` is passed, so existing installs
are unchanged. A2, if adopted later, would add
`experimental.subagent_depth: 2` behind the same flag.

## Compatibility

- OpenCode V1 and every non-bootstrap skill stay unchanged.
- The default install remains draft-and-review only.
- No model is pinned. The adapter leaves model selection to the OpenCode
  session default.
- Uninstall removes the scout agent and the bootstrap permission rules with the
  rest of the generated agent files.
- The canonical skill and persona text are not edited.

## Testing and evidence

Offline checks:

- Generated agent list, modes, and permission rule counts.
- No legacy keys in the generated configuration.
- `--enable-bootstrap` is the only way to add the new agent.
- Link integrity and table rendering for this document and the adapter guide.

Live checks, opt-in and recorded separately:

- A small fixture tree at or below five directories.
- A medium fixture tree between six and fifteen directories, including the
  safety gate pause.
- A large fixture tree above fifteen directories, including refusal and
  approval paths.
- Scout isolation: `.env` read denied, write denied, shell denied, outside
  project denied, MCP denied.
- Artifact check: every expected contract file exists and no source file
  changed.
- Fresh-context check: a parent-only marker is absent from scout output.

Do not mark the harness supported until installation, workflow, and isolation
results are recorded separately with the host version, model, and candidate
commit.

## Risks and mitigations

| Risk | Mitigation |
| :--- | :--------- |
| Primary context grows with many summaries | Chunk scouts, cap concurrency, write output as files |
| Narrow edit glob matches too much | Validate matcher; fall back to `ask` |
| Inherited rules weaken scout isolation | Inspect effective config; probe denial live |
| Cost from many scouts | Concurrency cap and the 15-directory gate |
| Large-tree quality drops | Keep A2 as a follow-up if evidence requires it |
| Hidden regressions in other skills | Keep bootstrap opt-in; rerun the full unit suite |

## Alternatives rejected

- **Widen `edit` for the whole project.** Too much write authority for a
  documentation-only workflow.
- **Reuse reviewer agents as scouts.** Reviewers deny the discovery tools the
  workflow needs and carry review-specific prompts.
- **Raise `subagent_depth` first.** It changes global delegation behavior for
  every agent, not only EGM, before a smaller design is proven.
- **Ship the SDK plugin first.** It adds a new distribution and security surface
  before the simpler path is tested.

## Implementation status

A draft implementation exists behind `--enable-bootstrap` in
[`install_win.py`](../../adapters/opencode/install_win.py). It adds the read-only
scout, the contract-write envelope, and the bootstrap dispatch rules.

On 2026-11-08, OpenCode 2.2.6 ran the implementation over a 3-directory fixture
and a 17-directory fixture. The small run produced four contracts with source
byte-identical. The large run paused at the gate with zero writes, then wrote 18
contracts after a structured question-form approval, using 16
`egm-goldfish-scout` child sessions in four waves of four without partition
workers. A probe child was denied `.env` and external reads, exposed no write,
shell, or MCP tools, and reported `UNKNOWN` for a parent-only marker.

A live brainstorm run then exposed a regression: a blanket `edit: deny` blocked
`concepts_brief.md`. The envelope now keeps `edit: ask` for non-contract
artifacts and allows only `README.md` and `EGM.md` without a prompt.

Live brainstorm, draft, and review also completed on 2026-11-08. Brainstorm
dispatched seven lenses and wrote `concepts_brief.md`. Draft wrote
`design_draft.md` in incremental sections. Review wrote five stage reports and a
consolidated report from eight reviewers, with seven dispatched in one parallel
wave; the sequential preset remains the canonical default. No source files were
modified.

Structured approval was exercised in the web UI: the safety-gate form rendered
with both options, a deliberate click selected "Yes", and the answer was
recorded. With no UI attached, the form stayed pending; selecting "No" aborted
with zero contract writes. The server does not auto-answer.

## Open questions

- Does OpenCode's path matcher support a narrow nested contract pattern, or must
  nested writes stay at `ask`?
- Should A1 spawn scouts sequentially or with bounded background sessions?
- Does the 15-directory gate need a structured question form, or is plain chat
  acceptable on every supported surface?
- Does a future SDK plugin need per-session permission rulesets to keep scouts
  read-only, and can that be verified in the host trace?
