# Metrics Log Provenance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make available-log metrics interpretable with content-free row quality and observed date bounds.

**Architecture:** Extend the existing retrieval scan and additive schema-2 export. Preserve legacy snapshots and privacy audit, with no observation filter or inference about missing daily history. Execute directly in this scheduled run under standing authorization; no separate execution handoff is needed.

**Tech Stack:** Python standard library, existing unittest suite and installed-wheel tooling.

---

## Scope and constraints

Standard task. No ranker/configuration changes, private archive access, work-PC upgrade, paid service, release, timestamp attribution or guessed lifetime coverage. Preserve existing original checkout and child memory indexes. Fields: log_available(bool), valid_events/malformed_events/blank_lines(counts), first_event_date/last_event_date(ISO date or null). Accepted events require search/show, valid calendar-date prefix and list-of-string returned IDs. Blank lines are counted separately; an invalid calendar date is malformed. Bounds are chronological min/max of accepted dates, independent of row order. Extra legacy fields remain ignored.

## Task 1: Behavioral regression tests

Modify tests/test_cli.py; add synthetic unordered mixed search/show logs with malformed JSON/scalars/shapes/invalid dates and blank rows. Assert exact aggregates, counts and dates. Test absent/empty/only-malformed logs, date-only legacy rows, privacy and unchanged schema-1 history. Run `PYTHONPATH=src python3 -m unittest discover -s tests -p test_cli.py` and confirm new tests fail before implementation.

## Task 2: Implement and document

Modify src/oldhand/analysis.py: add counters to existing scan, check calendar dates with datetime.fromisoformat(at[:10]), retain date-only legacy rows, expose min/max accepted dates and existence. Add fixed field names and date leaves to strict privacy allowlist; never allow arbitrary strings. Print row quality and date provenance even for no searches. Update docs/METRICS.md, docs/CLI_SPEC.md and CHANGELOG.md. Keep schema2 additive and legacy rows unchanged. Re-run targeted tests.

## Task 3: Verify and deliver

Run full unittest discovery, synthetic benchmark, distribution checker/build and isolated installed-wheel synthetic metrics/export. Audit no query/IDs/paths in export; confirm legacy history unchanged. Run diff check and staged Gitleaks. Review, commit focused change, fast-forward main, push and independently verify both remote SHAs. Update shared queue/profile/inventory/receipt and existing workspace memory, rebuild while preserving child indexes, release own lock. No package release.

Acceptance: known mixed logs produce exact quality/chronological bounds and existing rates; empty/missing logs have null bounds; malformed rows visibly counted; exports content-free and legacy snapshots unchanged; relevant full tests/benchmark/distribution pass.
