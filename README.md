# Lore

Durable engineering memory for coding agents, and the operating conventions
around it.

Start with **START_HERE.md**.

Lore is what a team knows about a system that never made it into the
documentation: the constraint nobody wrote down, the approach that looks
obvious and fails, the reason something surprising is the way it is. It is
expensive to acquire and it is normally lost when the session ends.

This archive holds that knowledge as Markdown, ranks it so the piece that
matters surfaces when its subject comes up, and retires it explicitly when it
stops being true. Recency carries no authority: a two-year-old invariant
outranks last week's debugging note.

The design has three principles:

1. Repository knowledge is canonical; harness integrations are adapters.
2. Models write knowledge; deterministic tooling should own bookkeeping.
3. Durable memory is selective and ranked, not a transcript of development.

What it deliberately does not hold: anything code, Git, tests, or current
documentation already preserve cheaply. A routine fix should produce no record
at all.

This package is tool-agnostic. `AGENTS.md` is the portable entry point.
`CLAUDE.md` is a thin Claude Code adapter. Other harnesses can add their own
adapters without changing the canonical policies.

**New here?** `START_HERE.md`, then `WRITING_RECORDS.md`. The second is short
and is where the quality comes from: on a real archive, retrieval tracked
summary quality far more closely than it tracked anything in the ranker.

**Adopting Lore with notes you already have?** Read
`RECONCILING_AN_EXISTING_ARCHIVE.md` before trusting the migrated result.
Separate archives disagree with each other, and the disagreements only become
a problem once they share one ranking.

**Trying it out?** `lore metrics --export` produces an anonymous health
bundle: counts and rates, no titles, ids, queries or topic names, and it
refuses to write if that is not true. Sending one back after a fortnight is
the most useful thing you can do for Lore, because every number in this
repository came from a single archive. See `METRICS.md`.

`LESSONS.md` records what building this taught us, including the parts that
were counter-intuitive and the measurements that overturned our assumptions.

```bash
python tools/install.py /path/to/your/archive   # puts `lore` on your PATH
python tools/lore/lore.py rebuild
python tools/lore/lore.py search "kafka partition key"
python tools/lore/lore.py validate
python tools/lore/lore.py new --title "..." --type constraint --importance high
```
