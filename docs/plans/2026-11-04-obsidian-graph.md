# Obsidian Graph Compatibility Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let users open their original Oldhand archive in Obsidian and see topic clusters and real record relationships.

**Architecture:** Extend the existing opt-in `oldhand obsidian` command. Add an owned Markdown section to original records with relative links, generate owned topic hubs, and refresh enabled archives before rebuilding the search index. Exclude generated sections from retrieval and preserve all authored content and metadata.

**Tech Stack:** Python 3.10+, standard library, existing Markdown/YAML records, Obsidian core graph view.

---

### Task 1: Native graph links and safe ownership

**Files:** Add `src/oldhand/obsidian.py`, update `src/oldhand/records.py` and `src/oldhand/search.py`, add `tests/test_obsidian.py`.

1. Add tests for direct relationship links, topic hubs, identical filenames across collections, Unicode and URL escaping, repeatable refreshes, and user-content preservation. Run them and confirm missing functionality fails.
2. Render relative standard Markdown links into a marked record section; keep typed relation labels readable. Use safe, deterministic topic filenames and explicit generated-note ownership. Refuse symlink escapes and conflicting user files before writing.
3. Preserve source frontmatter and prose exactly outside the owned section. Strip only that section from parsed retrieval content. Keep retired records visible as history.

### Task 2: Refresh after authoring

**Files:** Update `src/oldhand/indexing.py`, `src/oldhand/cli.py`, and `tests/test_e2e.py`.

1. Persist opt-in under `_topics/.oldhand.json`, outside derived SQLite state.
2. Refresh enabled archives before fingerprinting/rebuilding, without recursion. Handle graph failures as visible warnings during rebuild so search retains its existing fail-open behavior.
3. Test new/relate/unrelate/topic/rename/supersede and manual edits followed by rebuild. Ensure idempotence, unchanged metadata timestamps, and no generated text in search results.

### Task 3: Documentation, validation, and delivery

**Files:** Update `README.md`, `docs/CLI_SPEC.md`, and `CHANGELOG.md`; add `docs/OBSIDIAN.md`.

1. Document opening the archive root as a vault, graph/local graph, opt-in refresh, ownership, original-note editing, relation-type limitations, and source installation until the next PyPI release.
2. Run targeted Obsidian tests, `python3 -B tools/verify.py`, the synthetic benchmark verifier, build wheel/sdist, and smoke-test the installed wheel in a clean environment. Inspect diff and status.
3. Commit the focused feature branch, fast-forward merge into main, push main, and inspect CI. Do not publish a new PyPI version as part of this feature.

### Acceptance criteria

- Native Obsidian links resolve to actual source records across all collections, including duplicate basenames.
- Topic membership and typed relationships are reflected after Oldhand authoring commands or rebuild.
- Canonical metadata and authored prose survive refresh; generated links do not affect ranking.
- Existing user navigation files and Obsidian settings are preserved; no plugin or service is required.
- All existing and new checks pass. No live private archive is used as a public fixture.

### Baseline

`python3 -B tools/verify.py`: 187 tests and ranking selftest passed on Python 3.14.5 before changes. Main and origin/main start at `34e6f91`.

### Verification completed

- Final full suite: 209 tests and ranking selftest pass on Python 3.10 and 3.14.
- The deterministic synthetic retrieval benchmark matches its checked-in baseline.
- Wheel and source distribution build successfully with `uv build`.
- Clean Python 3.12 wheel installation passes init, graph opt-in, record creation,
  relationship linking, validation, and retrieval-isolation smoke checks.
- `git diff --check` passes. No separate lint/type-check configuration exists;
  the repository verifier checks Python 3.10 syntax compatibility.
- Native Obsidian visual testing is unavailable because the app is not installed.
- No version bump or PyPI publication is part of this change.
