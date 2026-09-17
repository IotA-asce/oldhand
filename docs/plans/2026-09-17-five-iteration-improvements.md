# Five Iteration Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Lore easier to query, automate, and browse through five additive CLI improvements, then replace the README with a visual, task-oriented product guide.

**Architecture:** Preserve Markdown as canonical state and SQLite as a derived index. Extend the existing read-only CLI paths with SQL predicates and structured renderers; do not change the schema, ranking constants, or record format. Each iteration begins with regression coverage and ends with targeted verification.

**Tech Stack:** Python 3.10+, argparse, sqlite3/FTS5, PyYAML, unittest, Markdown, SVG.

---

### Task 1: Filter search by record type

**Files:**
- Modify: `tools/lore/test_lore.py`
- Modify: `tools/lore/lore.py`
- Modify: `tools/lore/CLI_SPEC.md`

1. Add a failing test with two matching records of different types.
2. Run the targeted test and confirm the unfiltered result fails the expectation.
3. Add `--type` to `search` and apply `e.entry_type = ?` to both candidate passes and the empty-result count.
4. Run the targeted unit tests.
5. Commit as `feat: filter search by record type`.

### Task 2: Filter search by exact topic

**Files:**
- Modify: `tools/lore/test_lore.py`
- Modify: `tools/lore/lore.py`
- Modify: `tools/lore/CLI_SPEC.md`

1. Add a failing test with records whose searchable text matches but topics differ.
2. Add `--topic` with an exact, case-insensitive predicate through `entry_topics` and `topics`.
3. Ensure empty-result topic suggestions respect active collection/type/topic filters.
4. Run targeted search tests.
5. Commit as `feat: filter search by topic`.

### Task 3: Emit structured search results

**Files:**
- Modify: `tools/lore/test_lore.py`
- Modify: `tools/test_e2e.py`
- Modify: `tools/lore/lore.py`
- Modify: `tools/lore/CLI_SPEC.md`

1. Add failing tests for populated and empty JSON search results.
2. Add `--json` and emit one JSON document containing the query, active filters, count, and full result metadata.
3. Keep human output unchanged and keep retrieval logging identical for both renderers.
4. Run unit and end-to-end search tests.
5. Commit as `feat: add JSON search output`.

### Task 4: Emit a structured record

**Files:**
- Modify: `tools/lore/test_lore.py`
- Modify: `tools/test_e2e.py`
- Modify: `tools/lore/lore.py`
- Modify: `tools/lore/CLI_SPEC.md`

1. Add a failing test for `show --json`.
2. Query the indexed record and collection metadata, returning frontmatter fields, summary, body, path, and collection as JSON.
3. Preserve the existing raw-Markdown output when `--json` is absent.
4. Run unit and end-to-end show tests.
5. Commit as `feat: add JSON record output`.

### Task 5: Browse records without inventing a query

**Files:**
- Modify: `tools/lore/test_lore.py`
- Modify: `tools/test_e2e.py`
- Modify: `tools/lore/lore.py`
- Modify: `tools/lore/CLI_SPEC.md`

1. Add failing tests for active-only listing, filters, limits, and JSON.
2. Add `list` with `--history`, `--type`, `--topic`, `--collection`, `--limit`, and `--json`.
3. Sort deterministically by title then id and reject non-positive limits at argument parsing.
4. Run targeted tests, then `python3 -B tools/verify.py --clean-checkout`.
5. Commit as `feat: add record browsing command`.

### Task 6: Rewrite and illustrate the repository README

**Files:**
- Modify: `README.md`
- Create: `docs/img/workflow.svg`
- Create: `docs/img/cli-tour.svg`
- Modify: `.gitignore`

1. Replace the README with a shorter task-oriented narrative covering value, architecture, installation, the everyday loop, the complete CLI, evidence, privacy, development, and documentation map.
2. Reuse the existing measured charts and add two accessible SVG illustrations for the workflow and CLI tour.
3. Ignore macOS `.DS_Store` files without removing the user's existing untracked files.
4. Verify image links, command help, Markdown links, diff whitespace, and the full clean-checkout test suite.
5. Commit as `docs: rebuild the README as a visual product guide`.

### Delivery

1. Confirm only intended files are staged and no secrets or local artifacts are included.
2. Merge `feat/five-iteration-improvements` into `main` with a non-fast-forward merge.
3. Push `main` and the feature branch to `origin`.
4. Report commits, checks, merge/push results, and remaining risks.
