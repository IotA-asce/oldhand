# Evidence and evaluation

Oldhand makes a narrow promise: it keeps reviewed engineering knowledge in
readable, local files and helps a person or agent find it again. This page
separates what has been observed, what has been experimentally changed, and
what can be reproduced. They answer different questions and must not be
combined into a single product-performance claim.

## Evidence map

| Evidence type | Question it can answer | What it cannot establish |
| --- | --- | --- |
| Field observations | What happened in one maintained archive? | Typical results for other teams or archives |
| Controlled interventions | Did a particular change move a measured signal in that archive? | A universal ranking or curation rule |
| Synthetic benchmark | Does a known, repeatable corpus retain expected behavior across changes? | Real-world adoption, relevance, or recall |

## 1. Field observations: one archive

[`METRICS.md`](METRICS.md) reports operating measurements from one real
archive: 293 records in four collections, 47 searches across nine active days,
a 6% zero-result rate, and a 22% full-record open rate. Those numbers describe
that archive and its use; they are not a benchmark and should not be used to
forecast a new team's outcome.

In particular, coverage and open rate are behavioral signals, not quality
scores. An unopened result may have had an excellent summary, an irrelevant
summary, or no engaged reader at all. The metric reports the observed event,
not its cause.

The archive is intentionally not distributed as an evaluation corpus. Its
content may contain context that should not be published, and a private
archive cannot provide independent validation.

## 2. Controlled interventions: local causal evidence

[`LESSONS.md`](LESSONS.md) records interventions applied to the same
archive while holding the relevant comparison fixed where possible. Examples
include section indexing, identifier tokenization, summary repair, ranking
tuning, and critical-label inflation. These experiments informed implementation
choices such as keeping text relevance dominant and treating health checks as
advisory.

They are useful causal evidence for their stated setup. They are still not a
general-purpose leaderboard: the queries, records, and author knowledge came
from a single archive. The retrieval evaluation set is explicitly a regression
harness, not an unbiased benchmark; see the [CLI specification](../docs/CLI_SPEC.md#eval)
for its limits.

## 3. Reproducible synthetic benchmark: regression evidence

The versioned synthetic benchmark lives in
[`benchmarks/synthetic/`](../benchmarks/synthetic/). It uses fictional,
disclosure-safe records and fixed queries so contributors can repeat the same
measurement without access to a private archive. Run it with:

```bash
python -B tools/run_synthetic_benchmark.py --verify
```

Its checked-in result artifact is
[`benchmarks/synthetic/results.json`](../benchmarks/synthetic/results.json). Treat that
artifact as a regression baseline: it documents the corpus version, command,
and resulting metrics for a particular Oldhand revision. A change that moves a
baseline should explain why; it is not automatically a product improvement.

The synthetic benchmark is deliberately small and constructed. It can detect
determinism, indexing, scoring, and fixture-regression failures. It cannot
measure whether people remember to search, whether their knowledge is
well-curated, or whether results generalize to a production engineering
archive.

The related [`examples/sample-project/`](../examples/sample-project/) is a
short before-and-after demonstration, not a benchmark. It is also wholly
fictional; see its [synthetic-data notice](../examples/sample-project/SYNTHETIC_EXAMPLE.md).

## How to make a claim responsibly

- Label field observations as “one archive” and link to `METRICS.md`.
- Label an intervention with its corpus, comparison, and measured signal; link
  to `LESSONS.md` or the underlying evaluation material.
- Label synthetic results with the corpus version and result artifact.
- Do not average these sources together or describe any of them as an
  independent benchmark.
- Publish a new claim only when its inputs, command, and limitations are
  reviewable by someone outside the original archive.

Independent archives are the missing evidence. The privacy-preserving
`oldhand metrics --export` workflow is designed to make opt-in aggregate sharing
possible without sharing record text, queries, titles, paths, or identifiers.
It is not telemetry and sends nothing anywhere by itself.
