<div align="center">

# Lore

### Durable engineering memory for coding agents

**Discover it. Retrieve it. Connect it. Retire it when truth changes.**

Lore keeps the constraint nobody documented, the failed approach worth
avoiding, and the reason a surprising design is correct—then makes that
knowledge cheap enough to retrieve before the next agent rediscovers it.

[![version](https://img.shields.io/badge/version-0.4.4-bc8cff?style=flat-square&labelColor=0d1117)](https://github.com/IotA-asce/lore)
[![license](https://img.shields.io/badge/license-MIT-3fb950?style=flat-square&labelColor=0d1117)](LICENSE)
[![python](https://img.shields.io/badge/python-3.10%2B-58a6ff?style=flat-square&labelColor=0d1117)](tools/lore/requirements.txt)
[![dependencies](https://img.shields.io/badge/dependencies-1-8b949e?style=flat-square&labelColor=0d1117)](tools/lore/requirements.txt)
[![network](https://img.shields.io/badge/network-none-39c5cf?style=flat-square&labelColor=0d1117)](#design-guarantees)
[![storage](https://img.shields.io/badge/storage-Markdown-f0883e?style=flat-square&labelColor=0d1117)](#architecture)

</div>

Lore is a local-first memory layer for software work. Canonical knowledge stays
in ordinary Markdown. A disposable SQLite FTS5 index makes it searchable, and
the CLI returns a few ranked summaries rather than asking an agent to scan an
entire archive.

```bash
lore search "why did the consumer test pass without running"
lore show a-green-test-that-never-ran
```

![Markdown records flow through a disposable SQLite index into ranked summaries](docs/img/architecture.svg)

Delete `.lore/lore.db` and nothing canonical is lost. Lore rebuilds it from
Markdown.

## The problem it solves

An agent works inside a bounded session. When the session ends, expensive
context disappears: undocumented constraints, rejected approaches, failure
mechanisms, and rationale. Git says *what changed*. Current documentation says
*how the system works now*. Neither reliably answers:

> What should I know before I touch this again?

Lore owns only that question.

| Question | Canonical source |
|---|---|
| Which commit changed this? | Git, CI, tickets |
| How does it work today? | Current documentation |
| What am I doing right now? | Temporary task state |
| **What is expensive or dangerous to forget?** | **Lore records** |

Routine changes should produce no memory record. If code, tests, Git, or
current documentation preserve a fact cheaply, they will keep it current
better.

## Start in five minutes

Lore needs Python 3.10+, SQLite (included with Python), and PyYAML.

```bash
git clone https://github.com/IotA-asce/lore.git
cd lore
python3 -m pip install -r tools/lore/requirements.txt
mkdir -p ~/knowledge/memory
python3 tools/install.py ~/knowledge
```

Open a new terminal and check which archive Lore resolved:

```bash
lore stats
lore collections
lore topics
```

Create the first record:

```bash
lore new \
  --title "Config files replace instead of merge" \
  --type constraint \
  --importance high \
  --topics "configuration,deployment"

lore search "why did one new setting remove the old ones"
```

Nothing is installed system-wide. No administrator access, server, account, or
network connection is required. [INSTALL.md](INSTALL.md) covers PATH setup,
Windows, manual installation, and uninstalling.

## The complete lifecycle

![Discover, retrieve, create, connect, retire, validate, and measure Lore records](docs/img/lifecycle.svg)

Lore now supports the full practical loop:

1. **Discover** collection names and archive vocabulary.
2. **Retrieve** compact summaries and selectively open full records.
3. **Create** a record, or preview its exact Markdown first.
4. **Connect** related knowledge with typed relationships.
5. **Retire** knowledge explicitly when truth changes.
6. **Validate and measure** before repeating the loop.

Write only when forgetting would repeat expensive discovery, violate a
non-obvious constraint, or lose important rationale.

## Command tour

### Discover the archive

```bash
lore collections
lore collections --json
lore topics
lore topics --collection services/catalog --limit 25
lore list
lore list --type constraint --status current --topic deployment
```

`collections` reports active and total records plus topic counts. `topics`
lists the active vocabulary by frequency. Their output supplies the exact
names accepted by collection and topic filters, so users do not have to guess.

### Search and read

```bash
lore search "gateway retries"
lore search "gateway retries" --type decision --status current
lore search "gateway retries" --topic "API Gateway"
lore search "old authentication" --status superseded
lore search "gateway retries" --json
lore show <record-id>
lore show <record-id> --json
```

Search filters run before ranking and can combine status, type, topic,
collection, scope, history, and limit. Human output is compact; `--json`
emits one structured document to stdout while diagnostics remain on stderr.

![Lore serves readable terminal output and structured JSON through one local interface](docs/img/cli-tour.svg)

### Create safely

```bash
lore new \
  --title "Producer must set a partition key" \
  --type constraint \
  --importance critical \
  --risk critical \
  --durability invariant \
  --evidence verified \
  --topics "kafka,partitioning"

lore new --title "Preview me" --type lesson --importance normal --dry-run
lore new --title "Automate me" --type lesson --importance normal --json
lore new --title "Inspect me" --type lesson --importance normal --dry-run --json
```

`--dry-run` renders the exact proposed Markdown without creating a directory
or file. `--json` returns the generated id, path, collection, and creation
state; when combined with dry-run it includes the proposed content.

### Connect related knowledge

```bash
lore relate checkout-timeout caused_by gateway-retry-policy
lore relate checkout-timeout related_to payment-runbook
lore unrelate checkout-timeout related_to payment-runbook
```

Valid relationship types are `supersedes`, `depends_on`, `related_to`,
`caused_by`, and `contradicts`. Lore checks both ids, rejects self-links,
makes duplicate additions idempotent, updates the timestamp, validates the
archive, and rebuilds the derived index.

### Retire stale knowledge

```bash
lore status investigation-closed resolved
lore status obsolete-reference deprecated
lore status old-history historical
lore status revived-constraint current
lore supersede old-auth-model --by current-auth-model
```

`supersede` changes the old record to `superseded` and adds the replacement's
`supersedes` relationship as one validated operation. If either publication
fails, both original files are restored. The generic status command deliberately
cannot set `superseded`; that prevents a retired record with no replacement.

### Maintain and measure

```bash
lore validate      # strict schema, ids, sections, relations, supersession
lore rebuild       # regenerate the disposable index
lore doctor        # findability and summary health
lore conflicts     # possible contradictions and duplicate subjects
lore stats         # archive size and metadata distribution
lore usage         # what real retrieval has done
lore metrics       # privacy-audited health snapshot
lore eval          # retrieval against known answers
lore obsidian      # generated topic navigation
lore selftest      # ranking invariants
```

The complete CLI contract and rationale are in
[tools/lore/CLI_SPEC.md](tools/lore/CLI_SPEC.md).

## Ten improvement iterations

| # | Improvement | Outcome |
|---:|---|---|
| 1 | Search status filter | Query exactly one lifecycle state before scoring |
| 2 | List status filter | Browse current, resolved, historical, deprecated, or superseded records |
| 3 | Topic discovery | Learn active vocabulary and frequency instead of guessing filter values |
| 4 | Collection discovery | See exact collection names with active, total, and topic counts |
| 5 | JSON creation receipt | Automate creation without scraping terminal prose |
| 6 | Dry-run creation | Inspect exact Markdown without touching the archive |
| 7 | Add relationships | Validate ids and publish a canonical typed link safely |
| 8 | Remove relationships | Remove one link and prune empty relation groups |
| 9 | Atomic supersession | Retire the old record and connect its replacement together |
| 10 | Status transitions | Manage ordinary lifecycle states without hand-editing YAML |

These are interface and lifecycle changes. They do not change the record
schema, index schema, scoring constants, or the retrieval measurements below.

## Mutation safety

Read commands fail open so one malformed record cannot take retrieval offline.
Write commands take the opposite posture:

```text
validate existing archive
        ↓
resolve canonical ids
        ↓
build complete proposed frontmatter
        ↓
atomically replace file(s)
        ↓
validate the complete archive
   ↙ failure       success ↘
restore originals     rebuild SQLite
```

Lore refuses to mutate an already invalid archive. Markdown remains the source
of truth throughout; the index is rebuilt only after canonical state validates.

## Record format

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
created_at: 2026-09-18T10:00:00+05:30
updated_at: 2026-09-18T10:00:00+05:30
relations:
  depends_on:
    - deployment-loader
---

# Config files replace instead of merge

## Summary

Supplying one environment-specific config file replaces the complete base
mapping; it does not merge keys. Restate every required key in the override.

## Knowledge

The loader treats the selected file as the whole configuration source...
```

The summary is the retrieval surface: it is weighted heavily and is usually
all an agent reads. Write it for the question a future stranger will ask, not
as a diary of work performed. The measured guidance is in
[WRITING_RECORDS.md](WRITING_RECORDS.md).

## Architecture

Lore indexes whole records and meaningful `##`/`###` sections. It expands
code identifiers (`totalCost` becomes `total`, `cost`, and `totalCost`) and
uses two candidate passes: a bounded relevance pool and an unbounded safety
pass for critical knowledge. Results are deduplicated by record after scoring.

Text relevance contributes up to 60 points. All metadata combined contributes
at most 44. Labels break ties between comparable matches; they cannot make an
unrelated record win.

![Text relevance has a larger scoring budget than every metadata signal combined](docs/img/budget.svg)

Recency contributes nothing. An old invariant remains authoritative until it
is explicitly retired.

## Evidence, not intuition

Lore was tuned against a real archive of 293 records across four collections,
not a synthetic demonstration. Record quality and indexing granularity mattered
more than repeated ranker tuning.

![Retrieval before and after summary, identifier, and section indexing improvements](docs/img/beforeafter.svg)

| Intervention | Measured effect |
|---|---:|
| Stop admitting metadata blocks as summaries | 126 records repaired |
| Index sections as well as whole records | secondary-finding reachability 36% → 82% |
| Split code identifiers into words | two collections reached 100% recall@1 |
| Rewrite one weak summary | that record moved from unfindable → rank 1 |
| Three rounds of ranker tuning | one collection's recall@1 changed by 0 |

An aggregate score can hide a weak collection:

![Per-collection recall varies even when the archive average looks healthy](docs/img/collections.svg)

Health tools remain advisory. A first conflict detector flagged 29 items and
only four were genuine defects:

![First-pass conflict detection found four genuine defects among 29 flags](docs/img/precision.svg)

Read a flagged record before changing it. A false detection costs a minute; a
false automatic resolution silently destroys knowledge.

## Privacy and measurement

Commands append at most one daily archive-health snapshot to
`metrics/daily.jsonl`. Search and show events stay local in
`.lore/retrieval.jsonl`.

```bash
lore metrics --full
lore metrics --export mine.json
```

Exports contain counts, rates, percentiles, versions, timestamps, platform,
and schema values. They exclude titles, ids, paths, summaries, query text,
topic names, and collection names. Lore audits every string and refuses an
export containing anything outside the disclosure allowlist.

![Lore's measurement program moves from one archive toward independent validation](docs/img/stages.svg)

See [METRICS.md](METRICS.md) for the exact disclosure contract.

## Design guarantees

- **Local-first:** indexing, retrieval, and lifecycle commands need no network.
- **Portable:** Markdown and YAML remain useful without Lore.
- **Disposable index:** SQLite can always be rebuilt from canonical files.
- **Fail-open reads:** invalid records are reported and skipped while valid
  knowledge remains searchable.
- **Fail-closed writes:** mutation requires a valid archive and validates the
  complete result.
- **Rollback protection:** failed multi-record publication restores originals.
- **Stable automation:** search, show, list, topics, collections, and new offer
  structured JSON where automation needs it.
- **Measured invariants:** `lore selftest` guards scoring and retirement rules.

## Repository map

```text
.
├── memory/                    # example canonical archive
├── tools/lore/lore.py         # CLI, retrieval, and lifecycle engine
├── tools/lore/schema.sql      # disposable SQLite schema
├── tools/migrate/             # archive import and reconciliation
├── agent/                     # harness-neutral operating policies
├── docs/img/                  # README figures
├── docs/diagrams/             # editable draw.io sources
└── tools/verify.py            # syntax, unit, integration, invariant checks
```

| Read next | Purpose |
|---|---|
| [START_HERE.md](START_HERE.md) | Five-minute operating guide |
| [WRITING_RECORDS.md](WRITING_RECORDS.md) | Write records people can find |
| [INSTALL.md](INSTALL.md) | Install, configure PATH, and uninstall |
| [MIGRATING_AN_ARCHIVE.md](MIGRATING_AN_ARCHIVE.md) | Adopt Lore in phases |
| [RECONCILING_AN_EXISTING_ARCHIVE.md](RECONCILING_AN_EXISTING_ARCHIVE.md) | Resolve imported contradictions |
| [memory/SCHEMA.md](memory/SCHEMA.md) | Canonical record schema |
| [LESSONS.md](LESSONS.md) | What the project measured and learned |

## Development

```bash
python3 -B tools/verify.py
python3 -B tools/verify.py --clean-checkout
```

The verifier parses every Python file as Python 3.10, runs unit, migration,
installer, and end-to-end suites, then executes ranking self-tests. The
clean-checkout mode applies the current patch to a temporary clone without
stashing or resetting the working tree.

## Honest limitations

- Retrieval only helps when a human or agent actually searches. Give agents a
  concrete trigger: search before non-trivial work and when a surprise looks
  familiar.
- `compact` is not implemented. Supersession now safely retires individual
  records, but deciding when several records should be merged remains manual.
- Published measurements come from one archive. Privacy-audited exports exist
  to test whether the findings survive independent archives.
- Lifecycle commands preserve semantic YAML data but may normalize frontmatter
  formatting when they rewrite a record.

<div align="center">

Built to make rediscovery optional—and retirement explicit. MIT licensed.

</div>
