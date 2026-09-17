# Lore CLI

A working harness-neutral implementation ships with the package.

## Install dependency

```bash
python -m pip install -r tools/lore/requirements.txt
```

## Implemented commands

```bash
python tools/lore/lore.py init <path> [--json]
python tools/lore/lore.py validate [--json]
python tools/lore/lore.py rebuild [--strict]
python tools/lore/lore.py search "query"
python tools/lore/lore.py search --history "query"
python tools/lore/lore.py search "query" --collection <name> --scope <scope> --type <type> --topic <topic> --status <status> --importance <level> --limit N [--json]
python tools/lore/lore.py show <id> [--json]
python tools/lore/lore.py backlinks <id> [--json]
python tools/lore/lore.py list [--history] [--type <type>] [--topic <topic>] [--status <status>] [--importance <level>] [--collection <name>] [--limit N] [--json]
python tools/lore/lore.py topics [--collection <name>] [--limit N] [--json]
python tools/lore/lore.py collections [--json]
python tools/lore/lore.py stats
python tools/lore/lore.py selftest
python tools/lore/lore.py usage
python tools/lore/lore.py new --title "..." --type <type> --importance <level> [...]
python tools/lore/lore.py relate <source-id> <relation-type> <target-id>
python tools/lore/lore.py unrelate <source-id> <relation-type> <target-id>
python tools/lore/lore.py supersede <old-id> --by <replacement-id>
python tools/lore/lore.py status <id> <current|resolved|deprecated|historical>
python tools/lore/lore.py rename <old-id> <new-id>
python tools/lore/lore.py topic <id> (--add <topic> | --remove <topic>)
python tools/lore/lore.py classify <id> [--importance ...] [--scope ...] [--risk ...] [--durability ...] [--evidence ...]
python tools/lore/lore.py compact --into <target-id> <source-id>... [--dry-run] [--json]
python tools/lore/lore.py run-start --task <text> --evaluator <name> [--id <id>] [--policy <name>] [--goal maximize|minimize] [--workers N] [--workspace-ref <ref>] [--json]
python tools/lore/lore.py attempt-add <run-id> --id <attempt-id> --parent <root|attempt-id> --proposal <text> [--artifact-ref <ref>] [--policy-version <name>] [--json]
python tools/lore/lore.py attempt-evaluate <run-id> <attempt-id> --score N (--correct|--incorrect) --outcome <success|failure|error> [--cost N] [--duration-ms N] [--diagnostics-ref <ref>] [--json]
python tools/lore/lore.py run-finish <run-id> [--json]
python tools/lore/lore.py run-validate [<run-id>] [--json]
python tools/lore/lore.py runs [--status active|completed] [--json]
python tools/lore/lore.py run-show <run-id> [--json]
python tools/lore/lore.py doctor [--limit N]
python tools/lore/lore.py conflicts
python tools/lore/lore.py eval [--save <name>] [--against <name>]
python tools/lore/lore.py metrics [--full] [--export <path>]
python tools/lore/lore.py obsidian
```

Each has its own section below. `lore --help` is authoritative if this list
and the parser ever disagree.

## Discovery experience

`lore run-start` creates a canonical discovery trace under `experience/runs/`.
Traces are deliberately separate from distilled `memory/` records and from the
disposable `.lore/` index. A run records its task, fixed evaluator, exploration
policy, score direction, worker budget, and optional workspace reference.

`lore attempt-add` appends an immutable proposal node. Root may open several
branches; a non-root attempt has at most one recorded continuation so offline
replay can reveal the historical trajectory without ambiguous future choices.

`lore attempt-evaluate` attaches the fixed evaluator's grounded result exactly
once. Correctness is explicit and separate from score; cost, elapsed time, and
diagnostic artifacts remain available to replay and later audit.

`lore run-finish` closes only a nonempty run whose attempts all have grounded
evaluations. `run-validate` checks one trace or the entire experience archive,
including parent order, unique ids, continuation shape, score integrity, and
completion state.

`lore runs` is the deterministic discovery catalog, including attempt,
correctness, best-score, cost, and duration aggregates. `run-show` renders the
parent/continuation tree or returns the complete trace and a nested tree as
JSON.

## Initialize

`lore init PATH` creates a new archive with `memory/README.md` and an empty
derived index. It refuses to run when `PATH/memory` already exists, so it never
adopts or overwrites notes implicitly. Pass `--json` for a creation receipt
containing the resolved root, memory directory, and initial record count.

## Root resolution

`lore validate --json` returns record, error, and warning counts plus the full
diagnostic arrays. It preserves the human command's exit semantics: zero only
when the archive is valid.

The root is resolved in this order:

1. `--root PATH`;
2. the `LORE_ROOT` environment variable (set by `tools/install.py`, see
   `INSTALL.md`);
3. the **topmost** ancestor of the current directory containing `AGENTS.md` or
   `memory/`, stopping at the user's home directory.

Taking the topmost marker rather than the nearest one means running the CLI from
inside a repository still searches the whole workspace. Use `--root` to narrow
the scope deliberately. `stats` prints the resolved root so the scope of a query
is never ambiguous.

`schema.sql` is resolved relative to the script, not relative to the root, so the
CLI works from any directory without each repository carrying its own copy.

## Collections

A workspace may hold several memory archives. Every directory that owns a
`memory/` subdirectory is indexed as its own collection: the root, plus each
repository beneath it (searched to a depth of 4, skipping VCS, dependency and
build directories, and skipping the CLI's own directory).

One database at `<root>/.lore/lore.db` holds all collections. Record `id`
values must be unique across the whole workspace, not just within one
repository. Each collection gets its own generated `memory/MEMORY_INDEX.md`.

Restrict a query to one archive with `--collection <name>`, where the name is
the path shown by `stats` (`.` relative, for example `services/catalog`).

## Search behavior

Default search:

- uses SQLite FTS5 rather than asking the LLM to scan files;
- excludes `superseded` and `deprecated` records;
- returns ranked summaries rather than full bodies;
- combines textual relevance with topic, importance, risk, durability, status,
  and optional scope;
- gives recency no authority in v1.

Use `--type <type>` to restrict results to one record type, such as
`constraint`, `decision`, or `lesson`. The filter applies before ranking, so
scores are normalised only across records that can actually be returned.

Use `--topic <topic>` for an exact, case-insensitive topic match. Unlike adding
the topic words to the query, this is a true filter: records without that topic
never enter the ranking pool. Type, topic, collection, and history filters can
be combined.

Use `--status <status>` to select one lifecycle state exactly. An explicit
status overrides the default active-only behavior and `--history`, so
`--status superseded` returns only superseded records.

Use `--importance <level>` to restrict the candidate pool to one exact
importance level. It composes with every other search filter.

Pass `--json` when another tool or agent will consume the results. Lore emits
one JSON document with the query, active filters, result count, and result
objects. Each result includes its score, metadata, topics, collection, path,
token estimate, and complete summary. A miss is also a successful JSON
document and includes the number of records searched plus suggested topics.
Diagnostics still go to stderr, so stdout remains directly parseable.

`show <id>` prints the canonical Markdown record. With `--json`, it instead
emits one structured object containing every indexed frontmatter field,
topics, outgoing relations, collection, path, token estimate, summary, and
body. The JSON mode is read-only and records the same retrieval event as the
Markdown mode.

`backlinks <id>` inspects the record graph from both directions. It reports
each incoming and outgoing relation with the other record's title and status;
`--json` emits stable `incoming` and `outgoing` arrays for automation.

## List and browse

`lore list` browses records deterministically by title, then id, without
inventing a full-text query. It excludes superseded and deprecated records by
default; pass `--history` to include them. Exact type, topic, and collection
filters can be combined, and `--limit` bounds the output (50 by default).
An explicit `--status` selects that state exactly and overrides the active-only
default, including for retired states.
Use `--importance` to inventory one importance tier without a text query.

Human output is a compact catalog with metadata, topics, and summaries.
`--json` returns the matching count separately from the number returned, so a
caller can detect truncation. Listing is not written to the retrieval log:
that log measures intentional searches and record opens, not archive
administration.

`lore topics` discovers the vocabulary needed by exact topic filters. It lists
topics attached to active records, ordered by record count and then name.
Repeated topic names remain separate across collections. Use `--collection`
to narrow the catalog, `--limit` to bound it, and `--json` for a document that
separates the total matching count from the number returned.

`lore topic ID --add TOPIC` and `--remove TOPIC` safely curate a canonical
record's vocabulary. Matching is case-insensitive and space/hyphen aware;
Lore refuses to remove the final topic.

`lore classify ID` updates one or more ranking and governance fields in a
single validated write. Enum choices are enforced by the CLI parser.

`lore compact --into TARGET SOURCE...` is deliberately conservative: prepare
the target's canonical prose first, then Lore atomically marks every source
`superseded` and adds the reverse `supersedes` edges to the target. It never
merges or deletes prose. Use `--dry-run --json` to inspect the complete plan.

`lore collections` lists every indexed collection with its kind, active and
total record counts, and topic count. The command is the discovery companion
to `--collection`: its names are the exact values accepted by search, list,
topics, and new. Pass `--json` for one structured document.

Ranking runs in **two passes**:

1. a bounded relevance pool (the best 500 matches by BM25);
2. an **unbounded** safety pass over records that are `critical` importance, or
   `critical` risk with `invariant` durability.

The safety pass exists because a bounded pool alone silently breaks the
"critical knowledge always surfaces" guarantee as the archive grows: a critical
record that matches the query but ranks below the pool cut would never be
considered at all.

BM25 relevance is normalised across the merged candidate set onto a 0 to 60
range. Metadata contributes at most 44 on top, and that ceiling is deliberate:
**metadata breaks ties between comparable matches, it never decides the
ranking.** Criticality is a scoring weight and a display marker (`!`), not a
sort key.

The ceiling exists because the alternative was measured. An earlier build let
importance, risk and durability sum to 60, the entire text range, so a single
`critical` label was worth as much as a perfect textual match. On a
117-record archive, recall@5 fell from 92% to 33% once a quarter of records
carried that label, and nothing in the design resists label inflation: every
agent believes its own finding is critical.

Rebalancing fixed the collapse. Measured on the build that capped metadata at
52, the same corpus and queries held 83% to 67% across that range instead of
falling to 17%. The cap is 44 today, lowered when sweeping the importance
contribution from 12 to 4 raised findability from 92% to 95% and changed eval
recall and MRR by nothing at all. That sweep was measured; the full inflation
curve has not been re-run since, so read 83% to 67% as the figure for the 52
build rather than for this one.

`lore selftest` asserts these invariants. Run it after changing any scoring
constant; a single hand-checked query will not catch this class of regression,
because the failure is distributional rather than per-query.

Evidence contributes to the score. `verified` versus `inferred` is the only
metadata distinction that is checkable at write time rather than predicted,
which makes it the one worth trusting.

## Identifier expansion

`lore rename OLD NEW` changes a canonical record id and every incoming
relation reference in one validated transaction. It rejects collisions and
invalid portable ids; filenames are intentionally left stable.

Code identifiers are indexed by their component words as well as whole.
FTS5's tokenizer splits on punctuation and nothing else, so `totalCost` is the
single token `totalcost`, and the words "total" and "cost" do not match it.
Verified directly against the tokenizer:

```
"totalcost"  -> MATCH
"total"      -> no match
"cost"       -> no match
```

In an archive written alongside code that is not an edge case, it is most of
the vocabulary: `purchaseInfo`, `chainId`, `rulesVersion`, `resolvedPublisher`,
`ContractStatus`. Someone asking "the stored total cost looks wrong" could not
reach the record that says `EntitlementRecords.purchaseInfo.totalCost`, and
the empty result gave no hint why. It reads as the knowledge not existing.

Expansion is added to the column the identifier came from, so a name in a
title keeps title weight. Only identifier-shaped strings are touched: an
internal case change, an underscore, or a dot. Plain prose is never split,
because splitting it would invent terms the author did not write.

Measured on a 293-record archive: the `sam` collection went from 71% to 86%
recall@1 and `productdiscovery` from 88% to 100%, at the cost of three
prose-heavy queries slipping one rank each.

## Section indexing

`rebuild` indexes each record twice over: once whole, and once per `##`/`###`
section that names a finding and is long enough to be one. Every extra row
carries its parent's id, and search deduplicates by record, so the archive
gains reach without gaining results.

This exists because granularity, not size, was the real problem. Measured on a
293-record archive, querying the internal headings of large records returned
the right record only **36%** of the time: a record is one indexable unit
however many things it says, so its fourth finding competes using the whole
document's vocabulary and loses. With sections indexed that rose to **82%**,
and eval recall@3 went from 77% to 95%.

The alternative was splitting those records, and it is worse. Splitting is
irreversible, and the grouping is information: a record that gathers five
findings under one investigation is asserting they belong together. Retrieval
granularity should not dictate how knowledge is filed.

Section matches are discounted by a few points against whole-record matches.
Without it, long records won on breadth rather than relevance: the repository
collections carry 19.6 index rows per record against the workspace
collection's 2.5, one record has 48, and a record with 48 chances to match
outranks a record with one even when the latter is the definitive answer. A
main-row match means the record IS about the query; a section match means one
part of it mentions the query. Both should surface the record, only the first
should win a close contest.

The value is swept against eval, findability and reachability together, since
a penalty big enough to flatter eval undoes the reason sections exist.

Section rows carry the parent record's title alongside the section heading.
Without it, sections competed with their own parent and findability by record
title fell from 95% to 91%; with it, it rose to 98% and large records stopped
being penalised at all.

Nothing on disk changes. This is derived state, rebuilt from the same
Markdown, and deleting the database still loses nothing.

## Rebuild

`rebuild` recreates `.lore/lore.db`, populates FTS5, and regenerates each
collection's `memory/MEMORY_INDEX.md`.

It is **fail-open**: invalid records are skipped and listed on stderr, and the
rest of the archive is still indexed and searchable. One malformed record must
never take the whole archive offline. Pass `--strict` to exit non-zero when
anything was skipped, for CI.

Because fail-open must not mean fail-silent, `search`, `show`, and `stats` print
a note on stderr when the index was built with records excluded.

A **stale** index is reindexed automatically rather than warned about. A stale
index answers "No matching memory", which reads exactly like "this knowledge
does not exist", and that is the one wrong answer a memory system must never
give.

## Retrieval log

Every `search` and `show` appends one line to `.lore/retrieval.jsonl`:
timestamp, action, query, and the ids returned.

This is the only way to answer the questions that decide whether an archive is
working: which records are ever returned, which returned records are ever
opened, and how often a search finds nothing. The characteristic failure of a
memory archive is accumulating records nothing ever retrieves, which cost
tokens and add ranking noise forever, and that failure is invisible without
this log. It is derived state, local, and ignored by Git with the rest of
`.lore/`.

Diagnostic searches are not logged. `doctor` issues one search per record and
`eval` one per query; recording those would bury genuine traffic under tooling
and make `usage` measure itself. Only a search someone asked for is recorded.

A search with no hits reports how many records were searched and the busiest
topics in the archive, so an empty result can be told apart from a wording
miss. "No matching memory" on its own reads as "this knowledge does not
exist", which is the one wrong answer a memory system must never give.

## Metrics

Any command appends one snapshot per day to `metrics/daily.jsonl`: pure SQL
and a line count, silent, and never able to fail a command. Automatic because
daily metrics that need someone to remember are not daily metrics.

```bash
lore metrics                      # today
lore metrics --full               # plus findability and eval
lore metrics --export mine.json   # a bundle safe to share
```

The export carries counts, rates, percentiles and scores, and never titles,
ids, paths, summaries, query text, topic names or collection names. Topic and
collection names are excluded specifically because they describe products and
team structure more precisely than almost anything else in an archive.

This is enforced rather than promised: before writing, every string value in
the bundle must be a version, an ISO timestamp, the platform name, a schema
enum or the fixed disclosure note. Anything else and the export refuses to
write and names the field. On a 293-record archive the bundle held eleven
string values in total; everything else was numbers.

Diagnostic searches are excluded from the retrieval log that feeds these
numbers, so metrics never measure their own tooling. See `METRICS.md`.

## Doctor

`lore doctor` runs health checks that need no hand-written ground truth. The
eval set only measures questions someone thought to write down; doctor asks
what the archive can answer about itself.

The core check is **findability**: every record is queried by its own title,
and should come back first. One that loses to another record on its own title
will not be reached by a real question phrased in other words, and the winner
is named so the fix is a specific edit rather than a global knob.

It also flags summaries too thin to rank on, summaries that only restate the
title, and records large enough to behave like several.

Findability is the better tuning signal of the two, because it covers every
record and cannot be gamed by writing friendly queries. Check both before
changing a weight: a value that improves one and wrecks the other is fitted to
the measure, not to retrieval.

## Conflicts

`lore conflicts` finds records that disagree with each other or with
themselves. Run it after migrating an existing archive and before trusting the
result; see `RECONCILING_AN_EXISTING_ARCHIVE.md`.

Three classes, in descending order of how badly they mislead:

1. **The summary does not carry the correction.** The body corrects a claim
   the summary still states. Search shows summaries, so the stale claim is
   what gets returned and the correction is invisible to anything that does
   not open the record.
2. **Declared stale, still marked current.** The text says superseded or
   outdated; the status does not agree, so it still ranks as live knowledge.
3. **Near-duplicate subjects.** Vocabulary overlap on title and summary.
   Cross-collection pairs are marked, being the usual result of merging
   archives that were maintained separately.

Near-duplicate scoring uses Jaccard (shared tokens over total tokens), not
containment. Containment divides by the smaller record, so an eight-token
summary scored 75% against anything sharing six words, and one such record
produced four of eighteen reported pairs on its brevity alone.

Record resolutions in `reconcile.jsonl` at the archive root so a re-migration
does not discard them; see `RECONCILING_AN_EXISTING_ARCHIVE.md`.

A pair joined by any relation is not reported again. Someone read both records
and decided, and re-raising a settled question on every run is how a report
teaches people to stop reading it. Suppressed pairs are counted on their own
line rather than hidden, so "no conflicts" stays distinguishable from "all
conflicts already handled".

**Nothing is applied automatically.** An earlier version auto-retired class 2
and was wrong on two of four real candidates, because a record can announce
that it is stale and still be the live answer. Detection is automated;
resolution is not, and that asymmetry is deliberate: a wrong detection costs a
minute of reading, a wrong resolution costs knowledge, silently.

## Obsidian

`lore obsidian` generates navigation notes for viewing the archive as an
Obsidian vault. No conversion is involved: Markdown with YAML frontmatter is
already Obsidian's native format, so the archive opens as a vault as it is,
with every metadata field appearing as a native property.

What it adds is graph structure. Topics are frontmatter values rather than
links, so Obsidian draws no edge for them; a hub note per topic turns a flat
list into visible clusters and needs no plugin.

Output goes to `HOME.md` and `_topics/` at the archive root, never into
`memory/`. Lore only scans `*/memory/**`, so generated notes are invisible to
the index and can never fail validation. Re-run it after any rebuild.

## Eval

`lore eval` measures retrieval against `eval/queries.jsonl`, one JSON object
per line: `{"q": "...", "expect": ["<id>", ...]}`.

```bash
lore eval --save baseline       # record where things stand
lore eval --against baseline    # after a change: what moved, and which way
```

It reports recall@1/3/5 and MRR, marks queries that ranked worse than the
saved run with `!`, and exits non-zero when anything regressed, so it works as
a CI gate.

With more than one collection it also reports a per-collection breakdown.
Read that rather than the total: an archive can average 70% while one
collection sits at 50% and another at 88%, and the average sends you to tune
the ranker when the real problem is the summaries in one repository.

This is a regression harness, not an unbiased benchmark. Whoever writes the
queries knows the archive, so the absolute numbers flatter it. What it
measures honestly is change. Add a row every time a search in real work should
have found something and did not; those rows are worth more than any seeded
set, because nobody wrote the record with them in mind.

The first thing an eval set usually reveals is that some apparent retrieval
failures are badly worded queries. Check which before changing any weight.

## Usage

`lore usage` reads `.lore/retrieval.jsonl` and answers the question that
decides whether the archive is working: how much of it anything has ever
retrieved.

It reports searches run, the share that found nothing, records never returned,
and records returned but never opened. A record nothing retrieves costs tokens
to write, adds noise to every ranking afterwards, and has never been useful,
and that is invisible from the record itself.

The never-retrieved list is withheld until 50 searches have been logged.
Before that, "nothing has returned this" mostly means "nobody has asked yet",
and acting on it would retire useful records on no evidence.

`stats` warns when more than 10% of the archive is marked `critical`. That is
the measured point where the label stops discriminating; see the budget rule
in `agent/MEMORY_POLICY.md`.

## Validate

`validate` is the strict gate and exits 1 on any error. It checks:

- required metadata, enum values, unique IDs across all collections;
- required `## Summary` and `## Knowledge` sections;
- relation types, relation targets, and self-referencing relations;
- **supersession consistency**: a record declaring `supersedes: X` is an error
  unless `X` has status `superseded` or `deprecated`.

Without that last check, supersession is a two-step manual edit that nothing
verifies, and a replaced record keeps outranking the record that replaced it.

It also emits non-blocking warnings, for example a record marked `superseded`
that no other record claims to supersede.

## New

`lore new` writes a well-formed skeleton and generates the bookkeeping the
model should not be hand-writing: the `id`, both timestamps, the file location
derived from the entry type, and the required section headings.

```bash
python tools/lore/lore.py new \
  --type constraint --importance critical \
  --risk critical --durability invariant --scope repository --evidence verified \
  --topics "kafka,partitioning" \
  --title "Producer must set a partition key" \
  --collection services/inventory
```

The command refuses to overwrite an existing file and prints the path and id.
Fill in `## Knowledge`, `## Verification` and `## References`, then run
`rebuild`. Hand-written frontmatter was the main source of records that failed
validation, which is why this is the intended write path.

Pass `--json` to receive a single object containing `created`, `dry_run`, id,
path, and collection instead of the human follow-up instructions. Pass
`--dry-run` to print the exact proposed Markdown without creating directories
or files. Combining both returns the Markdown in the JSON object's `content`
field with `created: false`.

Use `--id ID` when an automation or migration needs a deterministic identity.
Portable ids are 1-128 characters, start with a letter or number, and contain
only letters, numbers, dots, underscores, and hyphens. Collisions are refused;
without `--id`, Lore keeps generating a unique id from the title.

## Relationship maintenance

`lore relate SOURCE TYPE TARGET` adds one typed relationship to the canonical
source record. Both ids must exist, self-relations are rejected, duplicates
are idempotent, and `supersedes` is reserved for the atomic lifecycle command
unless the target is already retired. Lore refuses to mutate an archive that
does not currently validate, updates `updated_at`, validates the proposed
state, publishes with rollback protection, and rebuilds the derived index.

`lore unrelate SOURCE TYPE TARGET` removes one existing relationship and
prunes the relation type when its final target is removed. Missing ids and
missing relationships are errors; successful changes use the same validation,
rollback, timestamp, and rebuild path as `relate`.

`lore supersede OLD --by NEW` performs the two sides of supersession together:
it changes `OLD` to `status: superseded` and adds `NEW supersedes OLD`. Both
ids and the replacement's active status are checked before anything is
written. Both files receive the same timestamp, validation sees the complete
transition, and any publication failure restores both originals.

`lore status ID STATUS` changes ordinary lifecycle states with the same safe
mutation path. It accepts `current`, `resolved`, `deprecated`, and `historical`.
`superseded` is intentionally excluded: that state is only valid together
with a replacement's `supersedes` relationship, so use the atomic command.
An idempotent status request succeeds without rewriting the file.
