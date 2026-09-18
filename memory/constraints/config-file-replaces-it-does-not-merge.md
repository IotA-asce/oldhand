---
schema_version: 1
id: lore_example_config_replaces
type: constraint
status: current
importance: critical
scope: workspace
risk: critical
durability: invariant
evidence: verified
topics:
  - config
  - deployment
created_at: 2026-02-03T10:00:00+00:00
updated_at: 2026-02-03T10:00:00+00:00
expires_at: null
relations: {}
---

# Fictional example: an environment file replaces shared defaults, not merge

## Summary

In this fictional example, adding one key to an environment's vars file silently drops every key it was
inheriting from the shared defaults file. The deploy succeeds, the service
starts, and the missing settings surface hours later as unrelated faults. Copy
the inherited block in whenever you add a key.

## Knowledge

The fictional deployment tooling treats a per-environment `example_vars` block as a
replacement for the shared one, not an overlay. The mental model most people
carry, from layered config systems that do merge, is wrong here and nothing in
the tooling corrects it.

**Why it cost a day.** The diagnosis went to the newly added key, because that
was the change. The fault was in the forty keys that stopped being passed.
Nothing logs what a config file did not set.

**How to apply.** After editing any per-environment vars file, diff the
rendered environment against the previous deploy, not against the file. The
file shows what you meant; only the rendered result shows what the container
gets.

## Verification

Confirmed by rendering both revisions and diffing the resulting environment.

## References

- fictional shared defaults and environment override
