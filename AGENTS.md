# Workspace Agent Instructions

This file is the portable entry point for all coding agents in this workspace.

## Ownership

This section is optional and ships empty on purpose. Fill it in only if this
workspace contains repositories an agent must never write to.

Owned repositories:
- (none listed, so no ownership restriction is in force)

While that list is empty, ownership imposes no restriction and normal
judgement applies. Once it names even one repository, everything absent from
it is read-only reference, and a non-owned repository must never be modified.

Do not leave placeholder names here. An agent reading an unfilled list can
reasonably conclude that it owns nothing, that every path is therefore
read-only, and that it should decline to edit the code it was asked to
change. That failure surfaces a session or two after setup and does not look
like a configuration problem.

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
