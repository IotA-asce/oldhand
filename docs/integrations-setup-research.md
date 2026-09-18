# Harness setup research

Research date: 2026-09-18. This note establishes only configuration surfaces
documented by each harness vendor. It does **not** claim that Lore currently
implements `lore setup`.

## Safe default for a future setup command

`lore setup <harness>` should be an opt-in, previewable change to files in the
current repository only. Its default must be `--dry-run`; it must show an
exact diff, require confirmation to write, preserve an existing configuration,
and provide an undo operation. It should not install hooks, change user-level
configuration, send archive contents to a service, or run a command on every
prompt.

The initial integration should give the agent a short, explicit instruction:
consult Lore before changing an area with uncertain constraints; use
`lore search` with task-specific terms; treat returned records as evidence to
inspect rather than unquestionable commands. This is a behavioral convention,
not an enforcement boundary.

## Verified targets

| Harness | Verified project surface | Conservative setup target | Important limit |
| --- | --- | --- | --- |
| Claude Code | `CLAUDE.md` or `.claude/CLAUDE.md`; `.claude/rules/*.md` for modular rules | Add a dedicated `.claude/rules/lore.md`, after presenting its content | `CLAUDE.md` is context, not enforcement. Do not install a hook by default. |
| Codex | Repository `AGENTS.md`; nested `AGENTS.md` or `AGENTS.override.md` are discovered along the working path | Add a marked Lore block to an existing root `AGENTS.md` only with explicit consent; otherwise report that no isolated project instruction target is documented | Do not modify `~/.codex` or change fallback filenames. |
| Cursor | Version-controlled `.cursor/rules/*.mdc`; root `AGENTS.md` is also supported for simple project instructions | Add `.cursor/rules/lore.mdc` as an `Agent Requested` rule | `.cursorrules` is legacy; do not create it. |
| OpenCode v2 | Project `AGENTS.md` | Add a marked Lore block to an existing root `AGENTS.md` only with explicit consent; otherwise report the required manual step | The v2 `opencode.jsonc` `instructions` array is documented as currently inactive. |

### Claude Code

Claude Code documents project instructions in `./CLAUDE.md` or
`./.claude/CLAUDE.md`, and documents `.claude/rules/` as the modular,
version-controlled place for project rules. Rules without `paths` frontmatter
load at session start, so a Lore rule should be short and must not inject a
large archive. Claude explicitly says these files are context rather than
enforced configuration. Its `UserPromptSubmit` hook can add context before
each prompt, but it blocks prompt processing and has a 30-second default
timeout; that makes it unsuitable as Lore's default integration.

If a repository already uses `AGENTS.md`, Claude Code documents a
`CLAUDE.md` import (`@AGENTS.md`) as a compatibility approach. A future setup
must not add that import blindly: it changes the whole Claude instruction
context and can create duplicate or conflicting guidance.

Sources: [Claude Code memory and project instructions](https://code.claude.com/docs/en/memory), [Claude Code hooks](https://code.claude.com/docs/en/hooks).

### Codex

Codex documents `AGENTS.md` as the repository instruction mechanism. It
discovers one instruction file per directory from the repository root to the
current working directory, preferring `AGENTS.override.md`, then `AGENTS.md`;
nearer files appear later in the merged context. Its optional alternate
filenames are user configuration in `~/.codex/config.toml`, not a project
integration target for Lore.

There is no separately documented, isolated project rule directory in this
source. Therefore a safe first version should never create or rewrite an
unrelated `AGENTS.md`; it can add a clearly delimited, idempotent block only
after showing the diff and obtaining consent. If the file is absent, report a
manual instruction option instead of inventing a Codex-specific file.

Source: [OpenAI: AGENTS.md custom instructions](https://developers.openai.com/es-419/docs/agent-configuration/agents-md) (official documentation; localized page).

### Cursor

Cursor documents Project Rules in `.cursor/rules` as version-controlled MDC
files. An `Agent Requested` rule needs a `description` and is available for
the agent to include when relevant; this is the least intrusive verified rule
mode for Lore. Do not use an `Always` rule for a large record corpus. Cursor
also supports a root `AGENTS.md`, but `.cursor/rules/lore.mdc` avoids editing
a shared cross-harness instruction file. `.cursorrules` remains supported but
is explicitly deprecated.

The future generated rule should name only the local Lore CLI and its
read-only search workflow. It must not add an MCP configuration or grant
permissions: neither is necessary for the first integration.

Source: [Cursor Rules](https://docs.cursor.com/context/rules-for-ai).

### OpenCode

OpenCode v2 documents `AGENTS.md` as its persistent project guidance file and
explicitly states that V2 recognizes `AGENTS.md` only, not `CLAUDE.md` as a
fallback. It discovers nested instruction files while exploring a project.
It also explicitly warns that the `instructions` array in `opencode.jsonc` is
accepted by the schema but currently does not resolve files, globs, or URLs.

Accordingly, a setup command should not write `opencode.jsonc` for
instructions and should not claim success if only `CLAUDE.md` exists. The
safe, verified option is the same consented, idempotent block in root
`AGENTS.md` described for Codex.

Source: [OpenCode v2 instructions](https://opencode.ai/v2/docs/instructions).

## Explicit unknowns and non-goals

- No vendor documentation reviewed here establishes an official `lore setup`
  plugin format, command-registration API, or automatic retrieval protocol
  for all four harnesses. Do not imply one exists.
- An optional Lore MCP server remains a separate product decision. This
  research does not establish its transport, tool schema, permissions, or
  per-harness installation format.
- Hooks can be powerful but execute in a sensitive path. The first setup
  release should not install Claude hooks or any shell command that executes
  automatically.
- Instruction files influence model behavior; they do not guarantee retrieval
  or prevent unsafe actions. Safety controls must remain in Lore and in each
  harness's own permission model.

## Acceptance checks before implementation

1. Run each setup command in an empty fixture and a fixture with pre-existing
   instructions; confirm the latter is not overwritten.
2. Confirm `--dry-run` produces no filesystem change and output matches the
   later applied diff.
3. Confirm running setup twice is idempotent and `lore setup --undo` removes
   only Lore's delimited block/file.
4. Start each supported harness in the fixture and verify that its documented
   instruction file is discovered; record the harness version used.
5. Confirm setup does not write outside the repository and does not add a
   hook, MCP server, user configuration, network dependency, or credentials.
