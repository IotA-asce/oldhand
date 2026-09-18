# Ten Curation Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add ten onboarding, filtering, inspection, and safe curation improvements to Oldhand, complete the deferred compaction workflow, and rebuild the README as a visual end-to-end guide.

**Architecture:** Preserve Markdown/YAML as canonical and SQLite as derived. Read-only features query the existing index; mutation features reuse the validated, rollback-protected publication path. Compaction never invents or merges prose: it atomically retires selected source records into a user-prepared canonical target.

**Tech Stack:** Python 3.10+, argparse, sqlite3/FTS5, PyYAML, unittest, Markdown, SVG, draw.io XML.

---

### Iteration 1: Initialize an archive

**Files:** `src/oldhand/cli.py`, `tests/test_cli.py`, `tests/test_e2e.py`, `docs/CLI_SPEC.md`

1. Add failing tests for empty-directory initialization and refusal to overwrite an existing archive.
2. Add `init PATH [--json]`, creating `memory/`, a starter `memory/README.md`, and the first derived index.
3. Run targeted tests and commit `feat: initialize Oldhand archives`.

### Iteration 2: Accept deterministic record ids

**Files:** `src/oldhand/cli.py`, `tests/test_cli.py`, `tests/test_e2e.py`, `docs/CLI_SPEC.md`

1. Add failing tests for `new --id`, invalid ids, and collisions.
2. Validate ids against Oldhand's portable id syntax and bypass generated ids when supplied.
3. Run creation tests and commit `feat: support explicit record ids`.

### Iteration 3: Filter search by importance

**Files:** `src/oldhand/cli.py`, `tests/test_cli.py`, `docs/CLI_SPEC.md`

1. Add a failing exact-importance search test.
2. Add `search --importance`, applying the predicate before ranking and reporting it in JSON.
3. Commit `feat: filter search by importance`.

### Iteration 4: Filter list by importance

**Files:** `src/oldhand/cli.py`, `tests/test_cli.py`, `tests/test_e2e.py`, `docs/CLI_SPEC.md`

1. Add failing list and CLI tests.
2. Add `list --importance` and include it in JSON filters.
3. Commit `feat: filter record listings by importance`.

### Iteration 5: Inspect relationship backlinks

**Files:** `src/oldhand/cli.py`, `tests/test_cli.py`, `docs/CLI_SPEC.md`

1. Add a failing test for incoming and outgoing typed relationships.
2. Add `backlinks ID [--json]`, returning both directions deterministically.
3. Commit `feat: inspect record backlinks`.

### Iteration 6: Rename record ids safely

**Files:** `src/oldhand/cli.py`, `tests/test_cli.py`, `tests/test_e2e.py`, `docs/CLI_SPEC.md`

1. Add failing tests for id replacement across the record and all incoming relations.
2. Add `rename OLD NEW`, rejecting invalid/colliding ids and updating every affected canonical file atomically.
3. Commit `feat: rename record ids safely`.

### Iteration 7: Curate topics

**Files:** `src/oldhand/cli.py`, `tests/test_cli.py`, `docs/CLI_SPEC.md`

1. Add failing tests for topic add, remove, idempotence, and final-topic protection.
2. Add `topic ID --add TOPIC` and `topic ID --remove TOPIC` through the safe mutation path.
3. Commit `feat: curate record topics`.

### Iteration 8: Reclassify metadata

**Files:** `src/oldhand/cli.py`, `tests/test_cli.py`, `tests/test_e2e.py`, `docs/CLI_SPEC.md`

1. Add failing tests for importance, scope, risk, durability, and evidence changes.
2. Add `classify ID` with one or more enum-constrained metadata options.
3. Commit `feat: reclassify record metadata safely`.

### Iteration 9: Compact prepared records

**Files:** `src/oldhand/cli.py`, `tests/test_cli.py`, `tests/test_e2e.py`, `docs/CLI_SPEC.md`, `START_HERE.md`

1. Add failing tests for plans, dry runs, atomic batch retirement, invalid ids, and already-retired sources.
2. Add `compact --into TARGET SOURCE... [--dry-run] [--json]`; target must be active and sources remain on disk as superseded history.
3. Add all `supersedes` relationships to the prepared target, update one timestamp, validate, publish, and rebuild.
4. Commit `feat: compact records into a prepared target`.

### Iteration 10: Emit structured validation

**Files:** `src/oldhand/cli.py`, `tests/test_cli.py`, `tests/test_e2e.py`, `docs/CLI_SPEC.md`

1. Add failing success and failure tests for `validate --json`.
2. Emit one object containing validity, record count, errors, and warnings while retaining exit codes.
3. Commit `feat: add JSON validation output`.

### Documentation: Rebuild the README

**Files:** `README.md`, `docs/img/curation.svg`, `docs/diagrams/curation.drawio`

1. Rewrite the complete README around initialize, discover, retrieve, create, curate, consolidate, retire, and measure.
2. Add an accessible curation diagram with an editable draw.io source and reuse the existing architecture and measured-result visuals.
3. Document all ten iterations, safe compaction semantics, automation output, and remaining limitations.
4. Validate every local link and image.
5. Commit `docs: rebuild README around safe archive curation`.

### Delivery

1. Run `python3 -B tools/verify.py --clean-checkout`, CLI smoke tests, XML validation, link checks, and `git diff --check`.
2. Merge `feat/ten-curation-improvements` into `main` with a merge commit.
3. Push the feature branch and `main` to `origin`.
