# Workspace Safety

- Never modify non-owned repositories.
- Prefer explicit staging over broad staging commands.
- Do not weaken tests, validation, security boundaries, or invariants merely to make
  a task pass.
- Destructive Git operations require deliberate justification.
- Secrets must never be persisted in source, memory, implementation plans, or docs.
- Harness-specific hooks should enforce safety mechanically where possible, but the
  executable/checking logic should live in harness-neutral tooling.
- Treat generated memory indexes/databases as derived state, never canonical truth.
