# Installed Writing Guide Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver the bounded installed-guide slice of R1: offline writing advice and an installed create/find/retire walkthrough.

**Architecture:** Ship compact guide text in a Python module so wheel and sdist include it with the package. Dispatch `oldhand guide [topic]` before workspace discovery and metrics, keeping advice independent of archive state.

**Tech Stack:** Python standard library, argparse, unittest, existing Hatch packaging and distribution checks.

---

### Task 1: Specify and test the contract
Create tests/test_guides.py. `oldhand guide` lists writing, vocabulary, importance, lifecycle and exclusions; `oldhand guide TOPIC` prints that topic. Unknown topics exit 2. Patch workspace_root and record_daily_metrics to fail if called. No archive/root/index is required. Run the new tests and observe the missing-command failure.

### Task 2: Implement the bounded feature
Create src/oldhand/guides.py with static offline topic text and rendering. Add parser/early dispatch in src/oldhand/cli.py before root detection. No setup-block or ranking changes. Include exact existing CLI commands for creating, searching and retiring one synthetic record.

### Task 3: Validate installed delivery and document
Extend tools/check_distribution.py to run guide before archive creation, prove no archive is created, then create/find/retire a synthetic guide record with installed commands. Inspect wheel/sdist for guide module. Update docs/CLI_SPEC.md, WRITING_RECORDS.md and CHANGELOG.md. Run full verify, unchanged synthetic benchmark, uv build, distribution smoke and diff checks.

### Task 4: Deliver and record
Commit focused changes on feature/installed-writing-guide, fast-forward merge the clean main worktree and push source. Verify remote SHA. Mark concrete queue task completed with evidence, retain broad roadmap task queued, update portfolio inventory/profile and write run receipt. No package release, work-PC changes or setup-block claims.
