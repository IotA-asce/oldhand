# Workspace Agent Instructions

This file is the portable entry point for all coding agents in this workspace.

## Ownership

Define owned repositories explicitly here.

Owned repositories:
- `<OWNED_REPOSITORY_1>`
- `<OWNED_REPOSITORY_2>`

Everything else is read-only reference unless explicitly designated otherwise.

Never modify a non-owned repository.

## Canonical operating policies

Use the files under `agent/` as the canonical engineering policies:

- `agent/WORKFLOW.md`
- `agent/TASK_CLASSES.md`
- `agent/MEMORY_POLICY.md`
- `agent/DOCUMENTATION_POLICY.md`
- `agent/SAFETY.md`

Repository-level `AGENTS.md` files may define more specific rules for their subtree.

## Core operating rules

- Inspect existing code and relevant current documentation before substantial edits.
- Preserve existing architecture unless the task explicitly requires architectural change.
- Keep diffs focused; do not mix unrelated cleanup into feature work.
- Use the task class to decide how much planning is justified.
- Run targeted checks first and broader checks according to risk.
- Never claim verification that was not actually performed.
- Search memory when the task has historical dependence; do not preload the archive.
- Durable memory is selective. Do not record information that code, Git, tests, or current documentation already preserve cheaply.
- Harness-specific configuration may accelerate these rules but must not silently redefine them.

## Working state

- `implement/` is temporary task state and planning.
- `memory/` is selective durable learned knowledge.
- `documentation/` is current human-readable system truth.
- Git, CI, tickets, and source code are authoritative implementation evidence.
