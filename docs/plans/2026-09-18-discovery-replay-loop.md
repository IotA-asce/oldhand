# Discovery Replay Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a ten-iteration, Dream-RSI-inspired experience layer that records discovery trees, replays exploration policies offline, compares them on held-out histories, preserves diverse exploration context, and distills reviewed outcomes into Oldhand records.

**Architecture:** Keep `memory/` as distilled durable knowledge and add canonical JSON traces under `experience/runs/`. Put trace validation, mutation, replay, and comparison logic in `src/oldhand/experience.py`; expose it through the existing CLI without changing the memory or SQLite schemas. Replay is deterministic and prefix-only: policies may select from observations already revealed, while the environment reveals recorded children.

**Tech Stack:** Python 3.10+, argparse, JSON, pathlib, unittest, the existing atomic-write and CLI verification infrastructure.

---

### Iteration 1: Start a discovery run

**Files:** Create `src/oldhand/experience.py`; modify `src/oldhand/cli.py`, `tests/test_cli.py`, `tests/test_e2e.py`, `docs/CLI_SPEC.md`.

1. Write tests for `run-start`, portable ids, collision refusal, and JSON output.
2. Implement `experience/runs/<id>.json` with schema version, task, evaluator, policy, score goal, worker limit, timestamps, active status, and an empty node list.
3. Run targeted unit/E2E tests and commit `feat: start structured discovery runs`.

### Iteration 2: Record attempt nodes

**Files:** Modify `src/oldhand/experience.py`, `src/oldhand/cli.py`, tests, and CLI spec.

1. Write tests for root attempts, refinements, unknown parents, duplicate ids, and the single-continuation invariant for non-root nodes.
2. Implement `attempt-add RUN --id ID --parent root|ID --proposal TEXT [--artifact REF]` using atomic JSON publication.
3. Validate, test, and commit `feat: record discovery attempt nodes`.

### Iteration 3: Attach grounded evaluations

**Files:** Modify experience module, CLI, tests, and CLI spec.

1. Write tests for numeric score, correctness, outcome, cost, duration, diagnostics, and unknown/already-evaluated nodes.
2. Implement `attempt-evaluate RUN NODE --score N --correct|--incorrect --outcome TEXT` with non-negative cost and duration.
3. Validate, test, and commit `feat: evaluate discovery attempts`.

### Iteration 4: Finish and validate runs

**Files:** Modify experience module, CLI, tests, and CLI spec.

1. Write tests proving incomplete nodes prevent completion and malformed trace files are diagnosed.
2. Implement `run-finish` plus `run-validate [RUN] [--json]`, retaining non-zero exit codes for invalid histories.
3. Validate, test, and commit `feat: validate and finish discovery runs`.

### Iteration 5: Browse discovery history

**Files:** Modify experience module, CLI, tests, and CLI spec.

1. Write tests for deterministic run catalogs and tree-shaped run detail in human and JSON modes.
2. Implement `runs [--status] [--json]` and `run-show RUN [--json]` with aggregate attempt, correctness, score, and cost fields.
3. Validate, test, and commit `feat: browse discovery histories`.

### Iteration 6: Replay baseline exploration policies

**Files:** Modify experience module, CLI, tests, and CLI spec.

1. Build fixture trees where breadth-first, depth-first, and score-greedy policies reveal different prefixes.
2. Implement deterministic prefix-only replay with `replay RUN --policy breadth|depth|score-greedy --budget N`.
3. Return revealed nodes, rounds, batches, best correct score, and objective inputs; commit `feat: replay discovery policies offline`.

### Iteration 7: Balance quality, cost, and parallelism

**Files:** Modify experience module, CLI, tests, and CLI spec.

1. Write tests for maximize/minimize goals, cost penalties, worker-bounded batches, and parallelism bonuses.
2. Add `--beta-cost`, `--beta-parallel`, and `--workers` and compute `quality - beta_cost*attempts + beta_parallel*attempts/rounds`.
3. Validate, test, and commit `feat: score replay quality and cost`.

### Iteration 8: Compare policies with holdout histories

**Files:** Modify experience module, CLI, tests, and CLI spec.

1. Write multi-run tests with deterministic train/holdout splits and an incumbent included in every comparison.
2. Implement `policy-compare POLICY... [--holdout N] [--json]`, reporting mean train and holdout objectives without automatically changing policy files.
3. Validate, test, and commit `feat: compare replay policies on holdouts`.

### Iteration 9: Preserve exploration diversity

**Files:** Modify `src/oldhand/cli.py`, tests, and CLI spec.

1. Write tests for an `explore-context QUERY --workers N [--json]` pack.
2. Put critical constraints and critical invariants in `shared_guardrails`, directional history in one `history_guided` branch, and leave remaining branches independent.
3. Ensure no branch suppresses mandatory guardrails; validate and commit `feat: build diversity-preserving context packs`.

### Iteration 10: Distill reviewed outcomes into memory

**Files:** Modify experience module, CLI, tests, CLI spec, and README.

1. Write tests for `run-distill RUN NODE` dry-run and publication, provenance references, and evidence derived from evaluator correctness.
2. Reuse `new_record` so generated records follow the canonical schema and collision rules; require explicit title, type, importance, and topics.
3. Document the experience/replay loop and commit `feat: distill discovery outcomes into Oldhand`.

### Delivery

1. Run `python3 -B tools/verify.py --clean-checkout`, CLI smoke tests, JSON fixture validation, README link checks, and `git diff --check`.
2. Push `feat/discovery-replay-loop`, merge it into `main` with a merge commit, and push `main`.
