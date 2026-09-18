# Oldhand: ten generations of improvement

This log records the evolutionary run requested on 2026-09-18. Every generation
evaluates six independent, read-only candidates. Scores are out of 25: user
value, correctness/safety, repository evidence, compatibility, and
cost-to-benefit, each worth five points. Only three non-overlapping winners are
implemented and allowed to produce descendants.

## Generation 1 — establish the lineages

| Candidate | Focus | Score | Result |
|---|---|---:|---|
| A | reject non-positive `doctor --limit` | 19 | pruned |
| B | exclude direct shows from search open rate | 23 | pruned |
| C | replay root branches in a true worker batch | 24 | **survived** |
| D | audit metric object keys as well as values | 24 | **survived** |
| E | add privacy-audited `metrics --json` | 21 | pruned |
| F | prevent concurrent edits from blessing a stale index | 25 | **survived** |

Shipped:

- Rebuild fingerprints now describe the source snapshot parsed at the start of
  the build. A concurrent edit deliberately leaves a mismatch, causing the next
  indexed read to repair stale content.
- The metrics export auditor now rejects unknown object keys, closing a path by
  which archive-derived text could hide in a numeric field name.
- Multi-worker replay can open multiple independent root branches in one round
  without revealing any result before the batch is selected.

Verification: three focused regression tests plus the full project verifier.

## Generation 8 — make safe subsets usable

| Candidate | Focus | Score | Result |
|---|---|---:|---|
| A | filter policy comparisons by optimization goal | 25 | **survived** |
| B | reject invalid evaluator result semantics before mutation | 24 | **survived** |
| C | canonicalize duplicate dates in the source metric history | 24 | **survived** |
| D | reject invalid goals at run creation | 22 | pruned |
| E | reject non-finite replay coefficients | 23 | pruned |
| F | publish exports atomically | 22 | pruned |

Shipped:

- `policy-compare --goal` can select a homogeneous maximize or minimize cohort
  without weakening the default mixed-goal rejection.
- Attempt evaluation rejects non-boolean correctness and unknown outcome values
  before touching a trace.
- Daily upsert repairs all valid duplicate dates in the source history, keeping
  the latest snapshot for each date while preserving malformed rows for audit.

Verification: three focused regression tests plus the full project verifier.

## Generation 3 — reward reliable discovery

| Candidate | Focus | Score | Result |
|---|---|---:|---|
| H1 | rank policies by success coverage before conditional mean | 25 | **survived** |
| R1 | explore unseen branches before extending incorrect ones | 24 | **survived** |
| M1 | record end-of-command daily metric upserts | 24 | **survived** |
| H2 | chronological holdout variation | — | pruned (no result) |
| R2 | trace-validation variation | — | pruned (no result) |
| M2 | numeric export variation | — | pruned (no result) |

Shipped:

- Policy comparison prefers reliable training coverage before comparing the
  conditional mean objective; exact ties retain the incumbent.
- Score-greedy replay prioritizes correct frontiers, then unseen root branches,
  then continuations below incorrect attempts.
- Daily metrics are atomically replaced at process exit, so one row per day now
  reflects the latest completed command instead of the first command of the day.

Verification: three unit regressions, one end-to-end regression, and the full
project verifier.

## Generation 4 — make evidence portable across processes

| Candidate | Focus | Score | Result |
|---|---|---:|---|
| H1a | reject comparisons mixing maximize and minimize goals | 24 | pruned |
| R1a | reject non-finite replay coefficients | 23 | pruned |
| M1a | lock concurrent daily metric upserts | 22 | pruned |
| H1b | choose chronological holdouts across UTC offsets | 25 | **survived** |
| R1b | reject invalid numeric trace mutations before write | 25 | **survived** |
| M1b | prevent export from overwriting metrics history | 24 | **survived** |

Shipped:

- Trace timestamps must be offset-aware ISO-8601 values, and holdout selection
  sorts their actual instants rather than their textual representations.
- Evaluation mutation rejects booleans, fractions where integers are required,
  NaN, and infinity; the canonical JSON writer also forbids non-finite values.
- Metrics export refuses direct, normalized, symlink, or hard-link identity with
  its own daily history source.

Verification: three focused regressions plus the full project verifier.

## Generation 6 — bind evidence to identity and time

| Candidate | Focus | Score | Result |
|---|---|---:|---|
| A | validate node/evaluation temporal provenance | 25 | **survived** |
| B | reject invalid run goals at creation | 22 | pruned |
| C | strictly parse metric timestamps | 23 | pruned |
| D | bind trace id to filename | 25 | **survived** |
| E | reject invalid evaluator result semantics | 23 | pruned |
| F | exclude non-finite metrics and non-RFC JSON | 24 | **survived** |

Shipped:

- Node creation and evaluation times must fit inside the run envelope and no
  evaluation may occur after completion.
- Trace payload ids must match their filenames, preventing copied histories
  from silently becoming duplicate statistical samples.
- Metrics reject NaN and infinities while parsing, auditing, and serializing;
  exported JSON is strict and interoperable.

Verification: focused regressions plus the full project verifier.

## Generation 7 — make cohorts canonical

| Candidate | Focus | Score | Result |
|---|---|---:|---|
| A | canonicalize evaluator/policy/task identities | 24 | **survived** |
| B | reject boolean worker counts | 22 | pruned |
| C | collapse duplicate metric dates | 24 | **survived** |
| D | reject mixed optimization goals | 25 | **survived** |
| E | reject invalid goals at run creation | 22 | pruned |
| F | lock concurrent daily upserts | 21 | pruned |

Shipped:

- Run identity fields are trimmed at creation and imported traces with invisible
  surrounding whitespace fail validation.
- Policy comparison refuses to average maximize and minimize histories.
- Metrics exports retain only the latest valid snapshot for each calendar date,
  report duplicate counts, and emit chronologically ordered history.

Verification: three focused regressions plus the full project verifier.

## Generation 5 — preserve structural meaning

| Candidate | Focus | Score | Result |
|---|---|---:|---|
| H-deep | split holdout by evidence completion time | 25 | **survived** |
| R-deep | validate evaluator outcome fields before mutation | 23 | pruned |
| M-deep | reject structurally invalid metric-history rows | 24 | **survived** |
| H-adjacent | require a real evaluator identity | 24 | pruned |
| R-adjacent | reserve `root` as the tree sentinel | 25 | **survived** |
| M-adjacent | reject non-finite metric numbers | 23 | pruned |

Shipped:

- Out-of-time splits now use when a completed trace became available, preventing
  overlapping long-running discoveries from leaking future evidence.
- The attempt id `root` is rejected by both mutation and validation because it
  is the structural pseudo-parent used by rendering and replay.
- Export accepts only complete schema-1 daily snapshots; malformed or
  structurally incomplete JSON rows are counted, warned about, and excluded.

Verification: three focused regressions plus the full project verifier.

## Generation 2 — protect evidence from its own machinery

| Candidate | Focus | Score | Result |
|---|---|---:|---|
| F1 | stage generated indexes before database publication | 22 | pruned |
| D1 | refuse metrics exports over their source history | 21 | pruned |
| C1 | remove empty replay rounds | 24 | **survived** |
| F2 | roll back multi-collection generated indexes | 20 | pruned (duplicate F1) |
| D2 | validate retrieval events and bound open rate | 24 | **survived** |
| C2 | keep holdout results out of policy selection | 25 | **survived** |

Shipped:

- Replay no longer schedules observed leaves as empty work, so rounds,
  parallelism, and objectives remain truthful when budget exceeds trace size.
- Policy comparison always ranks on training histories; holdout histories are
  reported strictly as out-of-sample evidence.
- Metrics ignore malformed retrieval events, exclude deleted/unknown records,
  and calculate open rate only for records that search actually returned.

Verification: three focused regression tests plus the full project verifier.
