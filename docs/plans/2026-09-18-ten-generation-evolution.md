# Ten-Generation Lore Evolution Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve Lore through ten evidence-driven evolutionary generations, evaluating six independent candidate agents per generation and retaining only the strongest three lineages.

**Architecture:** Each generation begins from the same verified repository state. Six read-only candidate agents independently propose one bounded improvement; the root agent scores proposals for user value, correctness, evidence, compatibility, and implementation cost. The top three proposals are implemented as isolated changes, validated, and become the parent lineages for two varied descendants each in the next generation.

**Tech Stack:** Python 3.10+, SQLite FTS5, PyYAML, unittest, Markdown, Git.

---

## Evolution protocol

1. Run six candidates per generation in two waves of three because the execution environment permits three concurrent subagents alongside the root.
2. Keep candidates read-only so all six see a stable repository and cannot overwrite each other.
3. Require each candidate to return: problem evidence, smallest change, affected files, tests, risks, and expected benefit.
4. Score each candidate out of 25: user value (0–5), correctness/safety (0–5), repository evidence (0–5), compatibility (0–5), and cost-to-benefit (0–5).
5. Prune candidates that duplicate existing behavior, lack evidence, broaden scope materially, or cannot be validated.
6. Implement the three highest-scoring non-overlapping candidates as small patches.
7. Run focused tests after each patch and the full verifier at each generation checkpoint.
8. Clone each surviving lineage twice for the next generation: one descendant deepens the current direction; the other explores an adjacent variation.
9. Record the candidates, scores, winners, changes, and checks in `docs/evolution/ten-generations.md`.
10. After generation ten, run clean-checkout verification, update user-facing documentation for shipped behavior, commit, merge, and push.

## Generation loop

For generations 1 through 10:

1. Inspect the current verified baseline and define six independent candidate prompts.
2. Spawn candidates A–C, collect their reports, then spawn candidates D–F.
3. Score all six and select three non-overlapping winners.
4. Implement winner one with a focused regression test; run the focused test.
5. Implement winner two with a focused regression test; run the focused test.
6. Implement winner three with a focused regression test; run the focused test.
7. Run `python3 -B tools/verify.py` and record the generation checkpoint.
8. Define two varied descendants for each winner and begin the next generation.

## Final validation and delivery

1. Run documentation link and XML validation.
2. Run `git diff --check`.
3. Run `python3 -B tools/verify.py --clean-checkout`.
4. Commit with a conventional message.
5. Push the feature branch, fast-forward `main`, and push `main`.
