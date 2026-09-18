# Lore synthetic retrieval benchmark

This is a tiny, deterministic regression fixture for Lore's local retrieval.
It contains six fictional engineering-memory records and six hand-written
queries with binary relevance judgments. All fixture data is CC0 and explicitly
fictional; see [LICENSE.md](LICENSE.md).

Run it from a repository checkout:

```bash
python -B tools/run_synthetic_benchmark.py
python -B tools/run_synthetic_benchmark.py --verify
```

The runner copies the fixture to a temporary archive, rebuilds Lore's derived
SQLite index, calls `lore search --json` for each query, and emits canonical
JSON. `--verify` compares the fresh result with `results.json`; it is suitable
for CI. Regenerate an intentional baseline after review with `--write`.

## Metrics

`recall_at_1`, `recall_at_3`, and `recall_at_5` are the fraction of queries
with a judged relevant record in the first *k* results. `mrr_at_5` is the mean
reciprocal rank of the first judged relevant result, capped at five. The result
also includes each returned id and per-query rank so a regression is
inspectable instead of a single opaque score.

## Baseline and limits

`results.json` is a **regression baseline for this fixture**, not a benchmark
claim against other tools, not evidence of production accuracy, and not a
claim of general retrieval superiority. The corpus is deliberately small,
English-only, and authored alongside its queries. It does not model real
archive noise, changing vocabulary, multilingual search, user behavior, or
security outcomes. Use it to catch deterministic changes to this particular
retrieval contract; use a separate, representative and independently reviewed
dataset before making broader claims.
