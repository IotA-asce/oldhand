# Migrating an existing archive

Do not perform a big-bang rewrite.

## Preserve first

Keep the existing archive untouched until Lore retrieval proves itself.

## Phase 1. Install the operating model

Add:
- root `AGENTS.md`;
- thin `CLAUDE.md`;
- `agent/` policies;
- the record schema and tooling.

Do not migrate historical entries yet.

## Phase 2. Seed current knowledge

Identify only:
- critical invariants;
- high-value architectural decisions;
- active migrations;
- recurring traps;
- current subsystem summaries.

Convert those into Lore records.

Resist labelling all of them `critical`. A seeded archive is where importance
inflation starts, because everything selected for seeding felt important enough
to select. See the budget rule in `agent/MEMORY_POLICY.md`.

## Phase 2b. Reconcile

Before using the archive, find where it disagrees with itself:

```bash
lore conflicts
```

Two archives merged into one index will contradict each other, because they
drifted apart while nothing was comparing them. Those contradictions are
invisible until they share a ranking, and then search returns the confident
stale record just as readily as the correct one.

`RECONCILING_AN_EXISTING_ARCHIVE.md` covers what it finds, and why resolution
is never automatic.

## Phase 3. Use it on real work

For several weeks, use Lore for new tasks.

`.lore/retrieval.jsonl` records every search and show, so these are
queries against a file rather than impressions:

- how many records were created;
- average record size (`stats` reports token estimates);
- how often a search returned nothing;
- which records have never been returned by any search;
- which returned records were actually opened with `show`;
- cases where important history was missed.

The fifth of those is the one that decides whether the archive is healthy. A
record nothing has ever retrieved is pure cost: it consumes tokens at write
time, adds noise to every ranking afterwards, and has never once been useful.
If a large share of the archive is in that state, the memory-worthiness gate is
being applied too loosely, and no amount of ranking work will compensate.

## Phase 4. Lazy migration

When an old record is needed:
1. retrieve it;
2. decide whether it still contains durable value;
3. convert only the useful knowledge;
4. mark the old material as migrated or archived if desired.

## Phase 5. Compact

After enough records exist around one topic, create or update a topic summary.

The migration is successful when Lore becomes the default retrieval path
without losing important historical knowledge.
