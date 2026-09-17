<div align="center">

# Lore

### Durable engineering memory for coding agents

Keep the constraint nobody documented, the failed approach worth avoiding,
and the reason the surprising design is correct—then retrieve it before the
next agent pays to rediscover it.

[![version](https://img.shields.io/badge/version-0.4.4-bc8cff?style=flat-square&labelColor=0d1117)](https://github.com/IotA-asce/lore)
[![license](https://img.shields.io/badge/license-MIT-3fb950?style=flat-square&labelColor=0d1117)](LICENSE)
[![python](https://img.shields.io/badge/python-3.10%2B-58a6ff?style=flat-square&labelColor=0d1117)](tools/lore/requirements.txt)
[![dependencies](https://img.shields.io/badge/dependencies-1-8b949e?style=flat-square&labelColor=0d1117)](tools/lore/requirements.txt)
[![network](https://img.shields.io/badge/network-none-39c5cf?style=flat-square&labelColor=0d1117)](#what-lore-guarantees)
[![storage](https://img.shields.io/badge/storage-Markdown-f0883e?style=flat-square&labelColor=0d1117)](#how-retrieval-works)

</div>

Lore is a local-first memory layer for software work. Records are ordinary
Markdown, a disposable SQLite FTS5 index makes them searchable, and the CLI
returns a few ranked summaries instead of asking an agent to scan an archive.

```bash
lore search "why did the consumer test pass without running"
lore show a-green-test-that-never-ran
```

![Markdown records flow through a disposable SQLite index into ranked summaries](docs/img/architecture.svg)

The dependency points one way. Markdown is canonical; SQLite is a cache.
Delete `.lore/lore.db` and Lore rebuilds it without losing a record.

## Why Lore exists

An agent works inside a bounded session. When the session ends, expensive
context disappears: undocumented constraints, rejected approaches, failure
mechanisms, and rationale. Git can say *what changed* and documentation can
say *how the system works now*. Neither reliably answers:

> What should I know before I touch this again?

Lore owns only that question.

| Knowledge | Canonical home |
|---|---|
| Which commit changed this? | Git, CI, tickets |
| How does it work today? | Current documentation |
| What am I doing right now? | Temporary task state |
| **What is expensive or dangerous to forget?** | **Lore records** |

Routine changes should produce no Lore record. If code, tests, Git, or current
documentation preserve a fact cheaply, they will keep it current better.

## Five-minute start

Lore needs Python 3.10+, SQLite (included with Python), and PyYAML.

```bash
git clone https://github.com/IotA-asce/lore.git
cd lore
python3 -m pip install -r tools/lore/requirements.txt
python3 tools/install.py /path/to/your/archive
```

An archive is simply a directory containing `memory/`. To start empty:

```bash
mkdir -p ~/knowledge/memory
python3 tools/install.py ~/knowledge
```

Open a new terminal, then verify the resolved archive and create a record:

```bash
lore stats
lore new \
  --title "Config files replace instead of merge" \
  --type constraint \
  --importance high \
  --topics "configuration,deployment"
lore search "why did one new setting remove the old ones"
```

Nothing is installed system-wide, no administrator access is needed, and no
server, account, or network connection participates in retrieval. See
[INSTALL.md](INSTALL.md) for PATH setup, Windows notes, and uninstalling.

## The everyday loop

![Search, open selectively, work, and only write durable knowledge](docs/img/workflow.svg)

1. Search before non-trivial work and whenever something looks familiar or
   surprising.
2. Read summaries first; open the full record only when one earns attention.
3. Use current code and documentation to do the work.
4. Write a record only if forgetting the result would repeat expensive
   discovery, violate a non-obvious constraint, or lose important rationale.

This keeps retrieval cheap and prevents the archive from becoming a second,
stale copy of the repository.

## The CLI at a glance

![Lore serves concise terminal output and stable JSON through one local interface](docs/img/cli-tour.svg)

### Retrieve

```bash
lore search "gateway retries"                         # ranked active records
lore search "gateway retries" --type decision        # exact record type
lore search "gateway retries" --topic "API Gateway"  # exact topic
lore search "old auth" --history                     # include retired records
lore search "gateway retries" --json                 # one JSON document
lore show <record-id>                                 # canonical Markdown
lore show <record-id> --json                          # structured full record
```

Search filters run before ranking and can be combined with `--collection`,
`--scope`, and `--limit`. JSON is written as one document to stdout;
diagnostics remain on stderr so agents and scripts can parse it directly.

### Browse

```bash
lore list
lore list --type constraint --topic deployment
lore list --history --collection services/catalog --limit 100
lore list --json
```

`list` is deterministic—title, then id—and does not invent a search query.
Active records are the default; `--history` includes superseded and deprecated
ones. JSON reports both the total matching count and the number returned, so
callers can detect truncation.

### Write and maintain

```bash
lore new --title "..." --type lesson --importance normal
lore validate      # strict record and relationship validation
lore rebuild       # regenerate the derived index
lore doctor        # findability and summary health
lore conflicts     # possible contradictions and duplicate subjects
lore stats         # archive size and metadata distribution
lore usage         # real retrieval behavior
lore metrics       # privacy-audited health snapshot
lore eval          # retrieval against known answers
lore obsidian      # generated topic navigation notes
lore selftest      # ranking invariants
```

The full contract, flags, and rationale live in
[tools/lore/CLI_SPEC.md](tools/lore/CLI_SPEC.md).

## The five improvement passes

| Iteration | Improvement | Result |
|---:|---|---|
| 1 | Type-filtered search | Narrow retrieval to decisions, constraints, lessons, and other record types before scoring |
| 2 | Topic-filtered search | Match topics exactly and case-insensitively; zero-result guidance respects every active filter |
| 3 | JSON search | Consume hits and misses as stable structured documents without scraping terminal text |
| 4 | JSON show | Read indexed metadata, topics, relations, summary, and body as one object |
| 5 | Record browsing | Inspect a deterministic filtered catalog without manufacturing a full-text query |

These are interface improvements. They do not change the record schema,
ranking constants, or the measured retrieval behavior described below.

## What a record looks like

```markdown
---
schema_version: 1
id: config-files-replace-instead-of-merge
type: constraint
status: current
importance: high
scope: repository
risk: high
durability: long_lived
evidence: verified
topics: [configuration, deployment]
created_at: 2026-09-17T10:00:00+05:30
updated_at: 2026-09-17T10:00:00+05:30
relations: {}
---

# Config files replace instead of merge

## Summary

Supplying one environment-specific config file replaces the complete base
mapping; it does not merge keys. Restate every required key in the override.

## Knowledge

The loader treats the selected file as the whole configuration source...
```

The summary is the retrieval surface: it is heavily weighted and is usually
all an agent reads. Write it for the question a future stranger will ask, not
as a diary of the work performed. [WRITING_RECORDS.md](WRITING_RECORDS.md)
contains the measured guidance.

## How retrieval works

Lore indexes whole records and meaningful `##`/`###` sections. It expands
code identifiers (`totalCost` becomes `total`, `cost`, and `totalCost`), then
uses two candidate passes: a bounded relevance pool and an unbounded safety
pass for critical knowledge. Results are deduplicated by record after scoring.

Text relevance contributes up to 60 points. All metadata combined contributes
at most 44. That ceiling is a design constraint: labels break ties between
comparable matches; they cannot make unrelated records win.

![Text relevance has a larger scoring budget than every metadata signal combined](docs/img/budget.svg)

Recency contributes nothing. An old invariant remains authoritative until it
is explicitly retired; a recent note does not win merely because it is new.

## Evidence, not intuition

Lore was tuned against a real archive of 293 records across four collections,
not a synthetic demo. The clearest result was that record quality and indexing
granularity mattered more than repeated ranker tuning.

![Retrieval before and after summary, identifier, and section indexing improvements](docs/img/beforeafter.svg)

| Intervention | Measured effect |
|---|---:|
| Stop admitting metadata blocks as summaries | 126 records repaired |
| Index sections as well as whole records | secondary-finding reachability 36% → 82% |
| Split code identifiers into words | two collections reached 100% recall@1 |
| Rewrite one weak summary | that record moved from unfindable → rank 1 |
| Three rounds of ranker tuning | one collection's recall@1 changed by 0 |

Aggregate scores can still hide a weak collection:

![Per-collection recall varies even when the archive average looks healthy](docs/img/collections.svg)

Health tools are deliberately advisory. A first conflict detector flagged 29
items, but only four were genuine defects:

![First-pass conflict detection found four genuine defects among 29 flags](docs/img/precision.svg)

Read a flagged record before changing it. A false detection costs a minute; a
false automatic resolution silently destroys knowledge.

## Privacy and measurement

Every command can append one daily archive-health snapshot to
`metrics/daily.jsonl`. Retrieval events stay local in
`.lore/retrieval.jsonl`.

```bash
lore metrics --full
lore metrics --export mine.json
```

Exports contain counts, rates, percentiles, versions, timestamps, platform,
and schema values. They exclude titles, ids, paths, summaries, query text,
topic names, and collection names. Lore audits every string before writing an
export and refuses the file if a string is not explicitly allowed.

![Lore's measurement program moves from one archive toward independent validation](docs/img/stages.svg)

See [METRICS.md](METRICS.md) for the exact disclosure contract.

## What Lore guarantees

- **Local-first:** search and indexing require no network.
- **Portable:** Markdown and YAML remain useful without the CLI.
- **Disposable index:** SQLite can always be rebuilt from canonical files.
- **Fail-open retrieval:** invalid records are reported and skipped while valid
  records remain searchable.
- **Fail-loud diagnostics:** read commands warn when invalid records were
  excluded from the index.
- **Stable automation:** search, show, and list offer machine-readable JSON.
- **Measured ranking invariants:** `lore selftest` guards the scoring budget and
  retirement behavior.

## Repository map

```text
.
├── memory/                    # example canonical archive
├── tools/lore/lore.py         # CLI and retrieval engine
├── tools/lore/schema.sql      # disposable SQLite schema
├── tools/migrate/             # importers and reconciliation support
├── agent/                     # harness-neutral operating policies
├── docs/img/                  # README figures
├── docs/diagrams/             # editable draw.io sources
└── tools/verify.py            # syntax, unit, integration, and invariant checks
```

| Read next | Purpose |
|---|---|
| [START_HERE.md](START_HERE.md) | Five-minute operating guide |
| [WRITING_RECORDS.md](WRITING_RECORDS.md) | How to write records people can find |
| [INSTALL.md](INSTALL.md) | Installation, PATH behavior, and uninstall |
| [MIGRATING_AN_ARCHIVE.md](MIGRATING_AN_ARCHIVE.md) | Phased adoption plan |
| [RECONCILING_AN_EXISTING_ARCHIVE.md](RECONCILING_AN_EXISTING_ARCHIVE.md) | Resolve conflicts after importing notes |
| [memory/SCHEMA.md](memory/SCHEMA.md) | Canonical record format |
| [LESSONS.md](LESSONS.md) | What the project learned and measured |

## Development

Run the complete verifier with the active interpreter:

```bash
python3 -B tools/verify.py
```

To test a patch in a temporary clone without stashing or resetting the working
tree:

```bash
python3 -B tools/verify.py --clean-checkout
```

The verifier parses every Python file as Python 3.10, runs unit, migration,
installer, and end-to-end suites, then executes the ranking self-test. No
separate lint or static type-check configuration is currently provided.

## Honest limitations

- Retrieval only helps when a human or agent actually searches. Give agents a
  concrete trigger: search before non-trivial work and when a surprise looks
  familiar.
- `compact` and `supersede` are not implemented as commands. Validation and
  conflict detection support the manual lifecycle, but archive aging still
  requires judgment.
- The published measurements come from one archive. The metrics export exists
  to test whether the findings survive independent archives.

<div align="center">

Built to make rediscovery optional. MIT licensed.

</div>
