<div align="center">

# Oldhand

### Your code remembers what survived. Oldhand remembers why.

**Git-tracked institutional memory for coding agents.**

Reviewed constraints, decisions, failed approaches and operational hazards,
stored as readable Markdown and retrieved locally.

[![CI](https://github.com/IotA-asce/oldhand/actions/workflows/ci.yml/badge.svg)](https://github.com/IotA-asce/oldhand/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/oldhand?style=flat-square&labelColor=0d1117&color=bc8cff)](https://pypi.org/project/oldhand/)
[![license](https://img.shields.io/badge/license-MIT-3fb950?style=flat-square&labelColor=0d1117)](LICENSE)
[![python](https://img.shields.io/badge/python-3.10%2B-58a6ff?style=flat-square&labelColor=0d1117)](requirements.txt)
[![network](https://img.shields.io/badge/network-none-39c5cf?style=flat-square&labelColor=0d1117)](#what-oldhand-promises)
[![source](https://img.shields.io/badge/source-Markdown-f0883e?style=flat-square&labelColor=0d1117)](#two-kinds-of-memory)

*Keep the scar tissue. Preserve the reasoning. Replay the search.*

</div>

![Markdown knowledge and replayable experience flow through Oldhand into the next engineering task](docs/img/architecture.svg)

An engineering session leaves behind more than a diff. It leaves the constraint
that nearly broke production, the approach that failed for a non-obvious reason,
and the tiny piece of context that made the final solution possible. Most tools
preserve the result. Oldhand preserves the expensive part of getting there.

```bash
oldhand search "why did the consumer test pass without running"
oldhand show a-green-test-that-never-ran
```

Oldhand stores durable knowledge as ordinary Markdown, indexes it locally with
SQLite FTS5, and records structured discovery runs that can be replayed without
rerunning an agent or evaluator. Delete `.oldhand/`; the source survives.

> The point is not to remember everything. It is to stop paying twice for what
> mattered.

## Why Oldhand exists

Agents work inside bounded sessions. When the window closes, the most valuable
context is often the least likely to appear in code: rationale, rejected paths,
operational hazards, and exceptions to the obvious rule.

| If you need to know… | Look in… |
|---|---|
| What changed? | Git, CI, tickets |
| How does it work now? | Current documentation |
| What am I doing right now? | Temporary task state |
| **What is dangerous or expensive to rediscover?** | **Oldhand** |

Routine work should leave no Oldhand record. If code, tests, Git, or current docs
already preserve a fact cheaply, they will usually keep it current better. Oldhand
is for the knowledge that would otherwise disappear between sessions.

## See it work

![A terminal session: an agent asks why a config loader cannot be simplified, and the reviewed constraint comes back from the local archive](docs/img/demo-session.svg)

Everything above is real output from `examples/run_demo.py`, which runs
offline against a synthetic project. The image is generated from that command,
so it cannot drift from what the tool actually does:

```bash
python3 -B examples/run_demo.py     # the scenario
python3 -B docs/make_demo_svg.py    # redraw the image from its output
```

## Install

```bash
pipx install oldhand      # or: pip install oldhand
oldhand init ~/knowledge
export OLDHAND_ROOT=~/knowledge
```

> This is a **beta** (`0.6.0b1`), so `pip` needs `--pre` unless you pin the
> version. It has had no external users yet.

Python 3.10+ on Linux or macOS. No account, server, API key, model, or
network connection. Windows is not supported yet; see
[INSTALL.md](INSTALL.md).

Point your agent at the archive, then make the first memory:

```bash
oldhand setup claude          # also: codex, cursor, opencode

oldhand new \
  --id config-replacement-semantics \
  --title "Config files replace instead of merge" \
  --type constraint \
  --importance high \
  --topics "configuration,deployment"

oldhand search "why did one new setting remove the old ones"
```

`oldhand setup` prints the change it would make and writes nothing without
`--apply`. `oldhand init PATH` refuses to overwrite an existing `memory/`
directory. See [INSTALL.md](INSTALL.md) for a from-source install, shell
profile setup, and uninstalling.

## Why not just log everything?

Most agent-memory tools capture activity automatically and replay it back.
Oldhand does the opposite, for three reasons.

**It stores judgement, not transcripts.** A record exists because someone
decided a finding would be expensive to rediscover. Routine work leaves
nothing behind. An archive that captures everything ranks everything, and
ranking everything is how retrieval stops being useful.

**Markdown is canonical and the index is disposable.** Records are ordinary
files in your repository, reviewed in pull requests and diffed in Git. Delete
`.oldhand/` and nothing is lost; the next command rebuilds it. No database is
the source of truth, so there is nothing to migrate or export.

**Nothing leaves the machine.** No account, API key, embedding model, hosted
service, or background daemon. Retrieval is SQLite FTS5 over local files.

The distinction that matters in one line:

> Activity-capture tools remember what the agent did. Task trackers remember
> what work remains. Oldhand remembers what the engineering team learned and
> why it still constrains the code.

## The everyday loop

![Oldhand moves from discovery through retrieval, creation, curation, consolidation, and measurement](docs/img/curation.svg)

1. **Discover** the collections, topics, and lifecycle states already present.
2. **Retrieve** ranked summaries before doing non-trivial work.
3. **Create** only when a finding would be expensive to rediscover.
4. **Curate** identity, taxonomy, classification, and relationships.
5. **Consolidate** prepared knowledge without silently merging prose.
6. **Measure** findability and archive health, then repeat.

The source Markdown is always canonical. SQLite is only the lens that makes it
fast to search.

### Search before solving

```bash
oldhand search "gateway retries"
oldhand search "gateway retries" --type decision --importance high
oldhand search "old authentication" --status superseded
oldhand search "gateway retries" --topic "API Gateway" --json
oldhand show gateway-retry-policy --json
oldhand backlinks gateway-retry-policy
```

Search returns summaries first so an agent can decide what deserves context.
Type, topic, collection, status, and importance filters run before ranking.
`backlinks` exposes typed incoming and outgoing relations.

### Write for the future question

```bash
oldhand new \
  --id producer-partition-key \
  --title "Producer must set a partition key" \
  --type constraint \
  --importance critical \
  --risk critical \
  --durability invariant \
  --evidence verified \
  --topics "kafka,partitioning"

oldhand new --title "Preview me" --type lesson --importance normal --dry-run
```

The summary is the primary retrieval surface. Name the surprise, the consequence,
and the action. Do not write a diary entry. The measured guidance lives in
[WRITING_RECORDS.md](WRITING_RECORDS.md).

### Keep truth alive

```bash
oldhand topic producer-partition-key --add reliability
oldhand classify producer-partition-key --importance high --evidence verified
oldhand rename producer-partition-key kafka-producer-partition-key
oldhand relate checkout-timeout caused_by gateway-retry-policy
oldhand supersede old-cache-model --by current-cache-model

oldhand compact --into current-auth-model \
  old-auth-model legacy-auth-notes --dry-run --json
```

Compaction never invents a synthesis. Prepare the target record first; Oldhand then
retires the sources and adds reverse `supersedes` edges atomically. Old truth is
not deleted—it becomes history.

## Proof, not vibes

Oldhand’s published evidence comes from one real archive. That makes the numbers
useful engineering evidence, not a universal benchmark. The disclosure-safe
metrics format exists so independent archives can test whether these findings
travel.

### Observed archive snapshot

These are operational measurements from `METRICS.md`, not controlled benchmark
results.

| Signal | Observed value | What it says |
|---|---:|---|
| Records | **293** across **4** collections | one workspace, several knowledge domains |
| Index rows | **3,751** · 12.8 per record | section indexing exposes secondary findings |
| Record tokens | p50 **2,070** · p90 **5,704** · max **13,439** | the archive contains substantial records |
| Summary length | p50 **335** characters · **0** thin summaries | the retrieval surface is maintained |
| Searches | **47** over **9** active days | real usage, not synthetic query volume |
| Search misses | **6%** | most queries returned at least one candidate |
| Full-record open rate | **22%** | summaries usually prevented unnecessary opens |
| Archive coverage | **31%** | most records had not yet appeared in retrieval logs |
| Critical records | **4 / 293** · 1% | critical remains a scarce signal |

Coverage and open rate describe behavior, not quality. A low open rate may mean
excellent summaries—or weak user engagement. Oldhand reports the signal and avoids
inventing the story.

### Controlled interventions

The experiments in `LESSONS.md` isolate specific retrieval and curation changes.

| Intervention | Measured effect |
|---|---:|
| Reject metadata blocks masquerading as summaries | **126** records repaired |
| Index meaningful sections, not only whole records | secondary reachability **36% → 82%** |
| Split code identifiers into searchable words | two collections reached **100% recall@1** |
| Rewrite one weak summary | **unfindable → rank 1** |
| Tune the ranker for three rounds | one collection’s recall@1 changed by **0** |
| First-pass conflict detection | **4** genuine defects among **29** flags |

![Retrieval before and after summary, identifier, and section-indexing improvements](docs/img/beforeafter.svg)

The lesson was not “tune harder.” It was that the shape of the knowledge—good
summaries, searchable identifiers, reachable sections—matters more than another
round of ranking arithmetic.

### Critical cannot mean everything

In a controlled inflation test, recall@5 fell from **92%** with no records marked
critical to **17%** when half the archive carried that label.

![Recall declines as the share of critical records rises from zero to half the archive](docs/img/inflation.svg)

That result shaped Oldhand’s two-pass ranking model: a bounded text-relevance pool
plus an unbounded safety pass for truly critical knowledge. Text relevance can
contribute 60 points; all metadata combined is capped at 44. Metadata breaks
ties between plausible matches—it cannot make an unrelated record win.

![Text relevance has a larger scoring budget than all metadata signals combined](docs/img/budget.svg)

Health tools are intentionally advisory. The first conflict detector was right
only four times in 29 flags; automatic “cleanup” would have damaged the archive.

![Four genuine defects were found among 29 initial conflict flags](docs/img/precision.svg)

## Integrations

```bash
oldhand setup claude      # also: codex, cursor, opencode
```

`setup` prints the exact change it would make and writes nothing without
`--apply`. It only ever adds a small, marked instruction block telling the
agent to search before non-trivial work. It never creates hooks, MCP
settings, credentials, or user-level files, and `--undo` removes only content
it owns.

Any harness that can run a shell command can use Oldhand without a plugin:
`oldhand search "..."` is the whole interface.

## Two kinds of memory

Oldhand separates what happened from what deserves to endure.

```text
workspace/
├── memory/                  durable, reviewed Markdown
│   ├── constraints/
│   ├── decisions/
│   └── lessons/
├── experience/runs/         immutable discovery trees
│   └── planner-v1.json
└── .oldhand/                   disposable local machinery
    ├── oldhand.db
    └── retrieval.jsonl
```

**Durable memory** is the compact, reviewed truth future work should retrieve.
**Experience** is the larger tree of proposals, evaluations, costs, and outcomes
that lets Oldhand study *how* the answer was found. They meet only when a human
chooses to distill an evaluated result.

![A discovery task becomes a trace, is replayed under candidate policies, and can be distilled into durable memory](docs/img/replay-loop.svg)

The editable source is
[docs/diagrams/replay-loop.drawio](docs/diagrams/replay-loop.drawio).

## Replay discovery, not just conclusions

Oldhand 0.5.0 integrates the history-as-simulator insight from
[Dream-RSI](https://arxiv.org/abs/2609.14858): a grounded search history can be
reused to compare exploration policies offline. Oldhand adopts the practical idea,
not autonomous self-modification.

```bash
oldhand run-start --id planner-v1 --task "Tune query planner" \
  --evaluator bench-v2 --policy breadth --workers 4

oldhand attempt-add planner-v1 --id branch-a --parent root \
  --proposal "Replace nested scan with indexed lookup"

oldhand attempt-evaluate planner-v1 branch-a --score 81.4 --correct \
  --outcome success --cost 2 --diagnostics-ref results/branch-a.json

oldhand run-finish planner-v1
oldhand replay planner-v1 --policy depth --budget 20 --json
oldhand policy-compare depth score-greedy --incumbent breadth \
  --budget 20 --holdout 1 --evaluator bench-v2
```

A replay policy sees only the prefix it has revealed, never the full future
tree. Breadth, depth, and score-greedy baselines are deterministic. Comparison
keeps the incumbent visible, isolates newer histories as a holdout, and never
rewrites or promotes policy code automatically.

For parallel discovery, share guardrails without forcing every worker down the
same remembered path:

```bash
oldhand explore-context "query planner selectivity" \
  --workers 4 --history-branches 1 --json
```

Every worker receives critical constraints and invariants. Only selected
branches receive directional decisions and lessons; the others stay free to
explore. After review, close the loop:

```bash
oldhand run-distill planner-v1 branch-a \
  --title "Indexed lookup avoids nested planner scans" \
  --type lesson --importance high \
  --topics "database,performance" --dry-run
```

Distillation accepts only an evaluated node from a completed run, cites the
canonical trace, and uses the normal collision, validation, and dry-run safety
checks. The human still decides what becomes memory.

## How retrieval works

```text
Markdown records
      │
      ├── whole-record index
      ├── meaningful ## / ### sections
      └── identifier expansion: totalCost → total · cost · totalCost
      │
      ▼
SQLite FTS5 candidate set
      │
      ├── bounded relevance pass
      └── unbounded critical-safety pass
      │
      ▼
deduplicate by record → score → return summaries
```

Recency has no authority. An old invariant remains authoritative until someone
explicitly resolves, deprecates, or supersedes it. Malformed records are reported
and skipped so one bad note cannot take retrieval offline.

## The CLI, by intent

| Intent | Commands |
|---|---|
| Begin and verify | `init`, `validate`, `rebuild`, `selftest` |
| Discover | `collections`, `topics`, `list`, `stats` |
| Retrieve | `search`, `show`, `backlinks` |
| Create and classify | `new`, `topic`, `classify`, `rename` |
| Connect and retire | `relate`, `unrelate`, `status`, `supersede`, `compact` |
| Record experience | `run-start`, `attempt-add`, `attempt-evaluate`, `run-finish` |
| Inspect and replay | `runs`, `run-show`, `run-validate`, `replay`, `policy-compare` |
| Reuse experience | `explore-context`, `run-distill` |
| Diagnose and measure | `doctor`, `conflicts`, `usage`, `eval`, `metrics`, `obsidian` |

Most agent-facing reads and writes support `--json`; previewable mutations
support `--dry-run`. The complete contract is in
[docs/CLI_SPEC.md](docs/CLI_SPEC.md), and `oldhand --help` is
authoritative.

## Record anatomy

```markdown
---
schema_version: 1
id: config-replacement-semantics
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
  depends_on: [deployment-loader]
---

# Config files replace instead of merge

## Summary

Supplying one environment-specific config file replaces the complete base
mapping; it does not merge keys. Restate every required key in the override.

## Knowledge

The loader treats the selected file as the whole configuration source…
```

Stable ids make automation safe. Lifecycle state keeps history without letting
it pollute normal search. Evidence describes how strongly the claim is grounded;
importance describes how costly it is to miss. They are not the same thing.

## What Oldhand promises

- **Local-first.** Indexing, retrieval, replay, and curation require no network.
- **Portable.** Markdown and YAML remain readable without Oldhand.
- **Disposable machinery.** SQLite can always be rebuilt from canonical files.
- **Fail-open reads.** One malformed record does not take healthy memory offline.
- **Fail-closed writes.** Mutations require a valid archive and validate the
  complete result.
- **Rollback protection.** A failed multi-record publication restores every
  original file.
- **Explicit retirement.** Stale knowledge stays inspectable as history.
- **No autonomous promotion.** Replay produces evidence; people choose policy
  and durable memory.
- **Privacy-audited metrics.** Exports exclude titles, ids, paths, summaries,
  queries, topics, and collection names.

Mutation follows one conservative path:

```text
validate archive → resolve ids → build proposed state → publish atomically
                                                        │
                                  failure ───────────────┴──── success
                                     │                           │
                               restore files              rebuild index
```

Oldhand refuses to mutate an archive that is already invalid.

## Privacy and measurement

Search and show events remain local in `.oldhand/retrieval.jsonl`. At most one
daily health snapshot is appended to `metrics/daily.jsonl`.

```bash
oldhand usage
oldhand metrics --full
oldhand metrics --export mine.json
```

Exports contain aggregate counts, rates, percentiles, versions, timestamps,
platform, and schema values. Oldhand audits every string and refuses to export
anything outside the disclosure allowlist. The exact contract is in
[METRICS.md](docs/METRICS.md).

![Oldhand’s evidence program moves from one archive toward independent validation](docs/img/stages.svg)

## Honest limits

- Retrieval only helps when someone searches. Give agents a real trigger:
  search before non-trivial work and whenever a surprise feels familiar.
- Replay evaluates policies against recorded trees; it does not execute unseen
  proposals or prove a policy will generalize to a new task.
- Compaction does not synthesize prose. The target must already contain the
  intended canonical knowledge.
- Published measurements come from one archive. They are transparent findings,
  not claims of universal performance.
- Lifecycle commands preserve semantic YAML data but may normalize frontmatter
  formatting when rewriting a record.

<div align="center">

### Build the thing. Keep the reason.

MIT licensed. Local by design. Made for the next mind that opens the repo.

</div>
## Repository map

```text
.
├── memory/                    example canonical archive
├── experience/runs/           replayable discovery trees
├── src/oldhand/cli.py         CLI, retrieval, and curation engine
├── src/oldhand/experience.py   experience schema and replay logic
├── src/oldhand/schema.sql      disposable SQLite schema
├── tools/migrate/             import and reconciliation tools
├── agent/                     harness-neutral operating policies
├── docs/img/                  rendered README figures
├── docs/diagrams/             editable draw.io sources
└── tools/verify.py            full project verifier
```

| Read next | Purpose |
|---|---|
| [START_HERE.md](START_HERE.md) | the five-minute operating guide |
| [WRITING_RECORDS.md](WRITING_RECORDS.md) | write records people can find |
| [INSTALL.md](INSTALL.md) | install, configure PATH, and uninstall |
| [MIGRATING_AN_ARCHIVE.md](docs/MIGRATING_AN_ARCHIVE.md) | adopt Oldhand in phases |
| [RECONCILING_AN_EXISTING_ARCHIVE.md](docs/RECONCILING_AN_EXISTING_ARCHIVE.md) | resolve imported contradictions |
| [memory/SCHEMA.md](memory/SCHEMA.md) | canonical record schema |
| [LESSONS.md](docs/LESSONS.md) | the experiments and what they taught |

## Development

```bash
python3 -B tools/verify.py
python3 -B tools/verify.py --clean-checkout
```

The verifier parses every Python file as Python 3.10, runs unit, migration,
installer, and end-to-end suites, then executes ranking invariants. Clean
checkout mode applies the working patch to a temporary clone without stashing
or resetting the current tree.

