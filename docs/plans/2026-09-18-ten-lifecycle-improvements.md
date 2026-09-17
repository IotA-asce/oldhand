# Ten Lifecycle Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend Lore with ten additive discovery, automation, relationship, and lifecycle improvements, then rebuild the README as a visual guide to the complete workflow.

**Architecture:** Keep Markdown/YAML records canonical and SQLite derived. Read-only improvements query the current index; write improvements locate canonical records by id, update frontmatter and `updated_at`, validate the complete archive before publishing, and rebuild the index only after a successful mutation. Ranking constants, the database schema, and record schema remain unchanged.

**Tech Stack:** Python 3.10+, argparse, sqlite3/FTS5, PyYAML, unittest, Markdown, SVG, draw.io XML.

---

### Iteration 1: Filter search by status

**Files:** `tools/lore/lore.py`, `tools/lore/test_lore.py`, `tools/lore/CLI_SPEC.md`

1. Add a failing test with current and resolved matching records.
2. Add `--status` to `search`; apply it before ranking and expose it in JSON filters.
3. Run the targeted search tests.
4. Commit `feat: filter search by status`.

### Iteration 2: Filter list by status

**Files:** `tools/lore/lore.py`, `tools/lore/test_lore.py`, `tools/test_e2e.py`, `tools/lore/CLI_SPEC.md`

1. Add failing unit and CLI tests for exact status selection.
2. Add `--status` to `list`; an explicit retired status overrides the active-only default.
3. Run the targeted list tests.
4. Commit `feat: filter record listings by status`.

### Iteration 3: Browse topics

**Files:** `tools/lore/lore.py`, `tools/lore/test_lore.py`, `tools/lore/CLI_SPEC.md`

1. Add a failing test for topic counts, collection filtering, limits, and JSON.
2. Add `topics [--collection] [--limit] [--json]`, ordered by record count then name.
3. Run targeted tests.
4. Commit `feat: add topic discovery command`.

### Iteration 4: Browse collections

**Files:** `tools/lore/lore.py`, `tools/lore/test_lore.py`, `tools/lore/CLI_SPEC.md`

1. Add a failing test for collection record/topic counts and JSON.
2. Add `collections [--json]`, ordered by collection name.
3. Run targeted tests.
4. Commit `feat: add collection discovery command`.

### Iteration 5: Create records with JSON output

**Files:** `tools/lore/lore.py`, `tools/lore/test_lore.py`, `tools/test_e2e.py`, `tools/lore/CLI_SPEC.md`

1. Add a failing test for `new --json`.
2. Emit a single object with id, path, collection, and creation state while preserving human output by default.
3. Run creation tests.
4. Commit `feat: add JSON record creation output`.

### Iteration 6: Preview record creation

**Files:** `tools/lore/lore.py`, `tools/lore/test_lore.py`, `tools/test_e2e.py`, `tools/lore/CLI_SPEC.md`

1. Add a failing test proving `new --dry-run` writes no file.
2. Render the exact proposed record to stdout; support a JSON envelope when combined with `--json`.
3. Run creation tests.
4. Commit `feat: preview records before creation`.

### Iteration 7: Add record relationships

**Files:** `tools/lore/lore.py`, `tools/lore/test_lore.py`, `tools/test_e2e.py`, `tools/lore/CLI_SPEC.md`

1. Add failing tests for valid, duplicate, unknown, and self relationships.
2. Add a canonical-record mutation helper and `relate SOURCE TYPE TARGET`.
3. Update `updated_at`, validate, write atomically, and rebuild after success.
4. Commit `feat: add safe record relationships`.

### Iteration 8: Remove record relationships

**Files:** `tools/lore/lore.py`, `tools/lore/test_lore.py`, `tools/lore/CLI_SPEC.md`

1. Add failing tests for existing and missing relations.
2. Add `unrelate SOURCE TYPE TARGET`, pruning empty relation lists.
3. Validate and rebuild after mutation.
4. Commit `feat: remove record relationships safely`.

### Iteration 9: Supersede records atomically

**Files:** `tools/lore/lore.py`, `tools/lore/test_lore.py`, `tools/test_e2e.py`, `tools/lore/CLI_SPEC.md`, `START_HERE.md`

1. Add failing tests for `supersede OLD --by NEW`, including rollback on invalid ids.
2. Set the old status to `superseded` and add `NEW supersedes OLD` in one validated transaction across two Markdown files.
3. Update timestamps, publish both files atomically, then rebuild.
4. Commit `feat: supersede records atomically`.

### Iteration 10: Change record status safely

**Files:** `tools/lore/lore.py`, `tools/lore/test_lore.py`, `tools/test_e2e.py`, `tools/lore/CLI_SPEC.md`, `START_HERE.md`

1. Add failing tests for current, resolved, deprecated, and historical transitions.
2. Add `status ID STATUS`; reserve `superseded` for the atomic command.
3. Validate, write atomically, update the timestamp, and rebuild.
4. Commit `feat: manage record lifecycle status`.

### Documentation: Rebuild the README

**Files:** `README.md`, `docs/img/lifecycle.svg`, `docs/diagrams/lifecycle.drawio`

1. Rewrite the complete README around discover, retrieve, create, connect, retire, measure, and automate.
2. Add an accessible lifecycle diagram with an editable draw.io source; reuse the architecture and measured-result charts.
3. Document all ten iterations, mutation safety, JSON behavior, and remaining limitations.
4. Validate local links and diagram XML.
5. Commit `docs: rebuild README for the complete Lore lifecycle`.

### Delivery

1. Run `python3 -B tools/verify.py --clean-checkout`, `git diff --check`, CLI smoke tests, README link checks, and XML validation.
2. Merge `feat/ten-lifecycle-improvements` into `main` with a merge commit.
3. Push the feature branch and `main` to `origin`.
