# Task Classes

## Small

Use for:
- mechanical changes;
- isolated bug fixes;
- local refactors;
- clear single-purpose edits.

Expected artifacts:
- usually none under `implement/`.

Expected flow:
- inspect;
- edit;
- targeted verification;
- memory only if a non-obvious durable lesson was produced.

## Standard

Use for:
- meaningful feature work;
- multi-file fixes;
- behavior changes;
- moderate refactors.

Expected artifacts:
- `implement/<topic>/PLAN.md`.

The plan should contain:
- goal;
- scope;
- non-goals;
- likely affected areas;
- acceptance criteria;
- verification;
- important constraints.

## Architectural

Use for:
- migrations;
- new subsystems;
- cross-service contracts;
- high-risk refactors;
- data-model changes;
- security or compatibility boundaries.

Expected artifacts:
- `implement/<topic>/CORE_IDEA.md`
- `implement/<topic>/IMPLEMENT.md`
- `implement/<topic>/RULES.md`

Add rollback, migration, risk, or test plans when the change warrants them.

Task class may be promoted while investigating. It should not be inflated merely
because an agent prefers more ceremony.
