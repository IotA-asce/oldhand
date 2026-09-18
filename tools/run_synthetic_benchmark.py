#!/usr/bin/env python3
"""Run Lore's small, fictional retrieval-regression benchmark.

The checked-in result is intentionally a fixture baseline, not a quality claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "synthetic"
FIXTURE = BENCHMARK / "fixture"
QUERIES = BENCHMARK / "queries.json"
RESULTS = BENCHMARK / "results.json"
LORE = ROOT / "tools" / "lore" / "lore.py"
K_VALUES = (1, 3, 5)


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def fixture_digest() -> str:
    digest = hashlib.sha256()
    for path in sorted(FIXTURE.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(FIXTURE).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    digest.update(QUERIES.read_bytes())
    return digest.hexdigest()


def run_lore(archive: Path, *args: str, json_output: bool = True) -> dict | None:
    completed = subprocess.run(
        [sys.executable, "-B", str(LORE), "--root", str(archive), *args],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if completed.returncode:
        raise RuntimeError(
            f"lore {' '.join(args)} exited {completed.returncode}: {completed.stderr.strip()}"
        )
    if not json_output:
        return None
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"lore did not emit JSON: {completed.stdout!r}") from error


def score_query(result_ids: list[str], relevant_ids: set[str]) -> tuple[dict[str, float], float]:
    metrics = {
        f"recall_at_{k}": float(bool(relevant_ids.intersection(result_ids[:k])))
        for k in K_VALUES
    }
    rank = next((index for index, value in enumerate(result_ids[:max(K_VALUES)], 1)
                 if value in relevant_ids), None)
    return metrics, (1.0 / rank if rank else 0.0)


def run_benchmark() -> dict:
    specification = json.loads(QUERIES.read_text(encoding="utf-8"))
    queries = specification["queries"]
    with tempfile.TemporaryDirectory(prefix="lore-synthetic-benchmark-") as temporary:
        archive = Path(temporary) / "archive"
        shutil.copytree(FIXTURE, archive)
        run_lore(archive, "rebuild", json_output=False)
        per_query = []
        totals = {f"recall_at_{k}": 0.0 for k in K_VALUES}
        reciprocal_ranks = []
        for item in queries:
            response = run_lore(archive, "search", item["query"], "--limit", "5", "--json")
            result_ids = [entry["id"] for entry in response["results"]]
            metrics, reciprocal_rank = score_query(result_ids, set(item["relevant_ids"]))
            for name, value in metrics.items():
                totals[name] += value
            reciprocal_ranks.append(reciprocal_rank)
            per_query.append({
                "id": item["id"], "query": item["query"],
                "relevant_ids": item["relevant_ids"], "returned_ids": result_ids,
                "first_relevant_rank": int(1 / reciprocal_rank) if reciprocal_rank else None,
            })
    count = len(queries)
    return {
        "benchmark_id": specification["benchmark_id"],
        "corpus_sha256": fixture_digest(),
        "corpus_license": "CC0-1.0",
        "query_count": count,
        "result_limit": max(K_VALUES),
        "metrics": {**{name: round(value / count, 6) for name, value in totals.items()},
                    "mrr_at_5": round(sum(reciprocal_ranks) / count, 6)},
        "queries": per_query,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--verify", action="store_true", help="compare with checked-in baseline")
    action.add_argument("--write", action="store_true", help="replace checked-in baseline")
    args = parser.parse_args()
    result = run_benchmark()
    rendered = canonical_json(result)
    if args.write:
        RESULTS.write_text(rendered, encoding="utf-8")
    elif args.verify:
        if not RESULTS.exists() or RESULTS.read_text(encoding="utf-8") != rendered:
            print("synthetic benchmark baseline differs; review then run with --write", file=sys.stderr)
            return 1
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
