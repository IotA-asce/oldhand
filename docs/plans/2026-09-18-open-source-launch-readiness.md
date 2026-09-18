# Lore Open-Source Launch Readiness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn Lore from a strong private research repository into a safely publishable, installable, independently verified beta for coding-agent users.

**Architecture:** Keep Markdown as canonical data and SQLite as disposable derived state. First settle the public identity, then move the CLI behind an installable `src/` package with compatibility wrappers, add tested harness adapters and an optional MCP extra, and build trust through deterministic examples, CI, reproducible evidence, governance, and release artifacts. Replay remains supported but moves out of the core onboarding path into an explicitly experimental advanced guide.

**Tech Stack:** Python 3.10–3.13, `pyproject.toml`, PyYAML, SQLite FTS5, `unittest`, GitHub Actions, `build`, `twine`, pipx, Markdown, VHS/terminal recording, optional MCP Python SDK.

---

## Non-negotiable gates

Do not make the repository public until all P0 gates are green:

1. Canonical product, repository, distribution, import-package, and executable names are decided and checked.
2. Every branch and commit has been scanned; all examples are certified synthetic; any detected credential is revoked before history cleanup.
3. A clean machine can run `pipx install <distribution>`, `lore init`, and one harness setup command.
4. Required CI is green on Python 3.10–3.13 across Ubuntu, macOS, and Windows.
5. Community files, deterministic demo, changelog, signed/tagged beta release, wheel, and sdist exist.
6. At least three external beta users have completed the core workflow; installation blockers are closed.

The current evolutionary worktree is dirty on `feat/evolve-lore-ten-generations`. Finish or preserve that work before executing this plan; do not mix launch-preparation commits into it.

## Verified baseline (2026-09-18)

- The public-facing code and README say `0.5.0`; the newest Git tag is `v0.4.3`, and GitHub has no Releases.
- The reviewed `main` had 144 test methods; the in-progress evolution worktree currently contains 170. Neither count is independently trusted until CI runs it from the release commit.
- `tools/lore/lore.py` is now 3,772 lines; `experience.py` is already a separate 779-line module.
- There is no `pyproject.toml`, `.github/` workflow, package entry point, `examples/`, or required community file other than MIT `LICENSE`.
- The repository is private, with no topics, homepage, Discussions, or public demo. The existing README has many maintained diagrams, but no recorded end-to-end product demonstration.
- The current POSIX quickstart does not persist `LORE_ROOT` without `--shell-rc`; fish profile output is syntactically wrong; native Windows behavior is not proven by CI.
- The existing one-archive measurements are useful field evidence, not a reproducible general benchmark.

## Phase 0 — decide what is being launched

### Task 1: Record the product and naming decision

**Files:**
- Create: `docs/brand-decision.md`
- Modify after the decision: `README.md`, `pyproject.toml`, repository About metadata

**Steps:**

1. Build an availability matrix for the proposed public name, repository slug, normalized PyPI distribution, console command, import package, Homebrew formula, domain, and major social handles.
2. Record the known collisions: `lore`, `lore-memory`, and `lore-cli` are occupied on PyPI; “Lore agent memory” also overlaps directly with another SQLite/FTS5/MCP product.
3. Choose either a full rename or a qualified identity such as “Lore for Coding Agents.” Do not assume any candidate is available until the matrix is checked on execution day.
4. Run a basic trademark/confusion review with qualified counsel if this will become a commercial identity; document that the repository check is not legal clearance.
5. Decide separately: display name, GitHub slug, PyPI distribution, Python import, and executable. The executable may remain `lore` only if the collision tradeoff is explicitly accepted; otherwise provide a time-bounded compatibility alias.
6. Commit: `docs: record public identity decision`.

**Acceptance:** `docs/brand-decision.md` has one approved row, the rationale, owner, date, collision evidence, redirect/alias plan, and no unchecked launch-critical registry.

### Task 2: Freeze the positioning contract

**Files:**
- Create: `docs/product-positioning.md`
- Modify later: `README.md`, package metadata, GitHub About text

**Steps:**

1. Set the primary category to: “Git-tracked institutional memory for coding agents: reviewed constraints, decisions, failed approaches, and operational hazards stored as readable Markdown and retrieved locally.”
2. Preserve the line: “Your code remembers what survived. Lore remembers why.”
3. Add the competitive boundary: Claude-Mem remembers agent activity; Beads tracks remaining work; Lore preserves reviewed engineering learning and rationale. Describe Mem0 and Letta as broader state/memory platforms without making unverifiable superiority claims.
4. Declare non-goals: automatic transcript capture, general task tracking, hosted/vector memory, autonomous self-modification, and code indexing.
5. Define the initial customer profile: developers using Claude Code, Codex, Cursor, or OpenCode on repositories where operational constraints and failed approaches recur.
6. Commit: `docs: define Lore market position`.

**Acceptance:** a stranger can identify user, problem, mechanism, difference, and non-goals in under 30 seconds.

## Phase 1 — remove public-release hazards

### Task 3: Audit the complete history and make examples indisputably synthetic

**Files:**
- Create: `docs/security/history-audit-YYYY-MM-DD.md`
- Create: `.gitleaks.toml` only for documented false-positive allowlists
- Rename: `memory/reference/where-the-signing-key-lives.md` to a plainly fictional scenario
- Modify: all example records, `README.md`, `SECURITY.md`

**Steps:**

1. Mirror/fetch every remote ref and enumerate all branches, tags, commits, LFS objects, and deleted paths.
2. Run at least two independent full-history scanners (for example Gitleaks and TruffleHog) plus targeted searches for private keys, tokens, credentials, customer/employer names, internal domains, absolute home paths, and personal data.
3. Review every committed example and every historical version manually. Add a visible statement that all shipped examples, names, incidents, and metrics fixtures are synthetic.
4. Rename the signing-key example to something like `fictional-release-signing-key-location.md`; replace realistic infrastructure identifiers with obviously fictional values while preserving the teaching point.
5. For every finding: revoke/rotate first, then decide whether history rewriting is necessary. Record evidence and disposition without copying the secret into the report.
6. Run the scanners again against all refs and attach machine reports privately to the release checklist.
7. Commit: `security: certify public history and synthetic examples`.

**Acceptance:** zero unresolved high-confidence findings, every example has an owner-approved synthetic-data attestation, and the audit covers all refs—not only `HEAD`.

### Task 4: Move internal process artifacts out of the public product surface

**Files:**
- Move: `docs/plans/**` and `implement/**` to a private planning repository or a clearly labeled historical archive excluded from release artifacts
- Modify: `README.md`, `MANIFEST.in` or package include rules

**Steps:**

1. Classify each plan as useful public design history or internal execution residue.
2. Keep only durable design records under `docs/design/`; remove `implement/` from the release-facing root.
3. Ensure wheels/sdists include user documentation and licenses, not internal plans or private audit output.
4. Update every moved link and run a repository-local Markdown link checker.
5. Commit: `chore: separate product docs from internal plans`.

**Acceptance:** the root reads like a product repository, source distributions contain no internal task artifacts, and every local link resolves.

## Phase 2 — make installation ordinary

### Task 5: Correct the current installer and support claims

**Files:**
- Modify: `tools/install.py`, `tools/test_install.py`, `tools/test_e2e.py`, `README.md`, `INSTALL.md`

**Steps:**

1. Add failing tests proving the documented POSIX quickstart persists or explicitly exports `LORE_ROOT`; today the installer merely prints the export unless `--shell-rc` is supplied.
2. Add shell-specific profile rendering/parsing: POSIX shells use `export`; fish uses `set -gx`. Test install, repeat install, and uninstall without touching surrounding lines.
3. Check Windows `setx`/`reg` return codes and add native-Windows smoke coverage for paths containing spaces and non-ASCII characters.
4. Make installer changes transactional: a failed dependency check, environment update, launcher write, or `lore stats` probe must restore the pre-install state.
5. Add an explicit SQLite FTS5 capability check with an actionable error rather than claiming every bundled SQLite is sufficient.
6. Correct `INSTALL.md` and the README immediately; make pipx the primary path once Task 6 lands and label this script developer/legacy installation.
7. Commit: `fix: make installer claims and rollback reliable`.

**Acceptance:** the published quickstart resolves the intended archive from an unrelated directory in a fresh shell; zsh/bash/fish and native Windows evidence match every advertised platform claim; failed installs leave no owned artifacts.

### Task 6: Introduce the installable package without changing behavior

**Files:**
- Create: `pyproject.toml`
- Create: `src/<import_package>/__init__.py`, `__main__.py`, `cli.py`, `experience.py`, `schema.sql`
- Modify: `tools/lore/lore.py`, `tools/lore/experience.py`, tests, `tools/verify.py`

**Steps:**

1. Write failing tests that install a wheel into a temporary virtual environment and assert `lore --help`, `lore selftest`, `python -m <import_package> --help`, and resource loading all work outside the checkout.
2. Add PEP 517/621 metadata with an explicit build backend, the approved distribution name, `requires-python = ">=3.10"`, `PyYAML`, MIT license, classifiers, URLs, and `[project.scripts] lore = "<import_package>.cli:main"` (or the approved command).
3. Move runtime code/resources under `src/`; leave thin `tools/lore/*.py` compatibility wrappers for one release so old clone-based commands do not break silently.
4. Remove the duplicate runtime version string: expose one `__version__` used by CLI, metrics, README release tooling, and package metadata.
5. Build with `python -m build`; inspect wheel contents; run `python -m twine check dist/*`.
6. Test `pipx install dist/*.whl` in an isolated environment and exercise init/search/uninstall.
7. Run `python3 -B tools/verify.py --clean-checkout`.
8. Commit: `feat: package Lore as an installable CLI`.

**Acceptance:** wheel and sdist are reproducible from a clean checkout; neither requires the source tree at runtime; pipx installation produces the documented command on Linux, macOS, and Windows.

### Task 7: Split the monolithic CLI by domain

**Files:**
- Create under `src/<import_package>/`: `archive.py`, `index.py`, `retrieval.py`, `curation.py`, `metrics.py`, `experience.py`, `commands.py`
- Modify: `cli.py`, tests

**Steps:**

1. Add characterization tests for CLI return codes, stdout/stderr, JSON shapes, mutation rollback, and resource lookup before moving functions.
2. Extract archive parsing/validation and workspace discovery.
3. Extract SQLite schema, rebuilding, fingerprinting, and connection management.
4. Extract search, show, list, topics, collections, backlinks, and retrieval logging.
5. Extract record mutations and atomic publication.
6. Extract metrics/evaluation/doctor/conflicts.
7. Move the existing experience engine into the package unchanged, then expose it through command handlers.
8. Keep `cli.py` limited to parser construction, dependency wiring, dispatch, UTF-8 handling, and process-exit metrics.
9. Run focused tests after each extraction and commit each domain separately: `refactor: extract <domain> module`.

**Acceptance:** no runtime module is a 3,000+ line catch-all; public behavior and JSON contracts remain unchanged; full clean-checkout verification passes after every extraction.

## Phase 3 — meet agents where they work

### Task 8: Add deterministic harness setup commands

**Files:**
- Create: `src/<import_package>/setup.py`
- Create: `src/<import_package>/templates/{claude,codex,cursor,opencode}/...`
- Create: `tests/test_setup.py`
- Modify: CLI parser, `INSTALL.md`, `README.md`

**Steps:**

1. Specify the exact file each harness owns, the generated block, merge behavior, dry run, backup, idempotency, and uninstall path.
2. Write fixture-based tests for `lore setup claude|codex|cursor|opencode --dry-run`, first install, repeated install, user-customized surrounding content, malformed config, and rollback after write failure.
3. Implement setup as scoped, marked-block edits; never replace an entire user configuration file. Refuse ambiguous or unsupported formats with recovery instructions.
4. Add `lore setup <harness> --check` and `--remove`.
5. Validate generated configurations against each harness’s current documentation immediately before release.
6. Commit one adapter at a time: `feat: add <harness> setup adapter`.

**Acceptance:** all four commands are idempotent, reversible, dry-runnable, cross-platform where the harness supports it, and never destroy unrelated configuration.

### Task 9: Add an optional MCP server

**Files:**
- Create: `src/<import_package>/mcp_server.py`
- Add optional dependency group: `[project.optional-dependencies].mcp`
- Create: `tests/test_mcp_server.py`
- Create: `docs/integrations/mcp.md`

**Steps:**

1. Keep MCP optional so the default CLI retains one runtime dependency.
2. Expose the smallest useful read-first tool set: search, show, list/topics, and optionally safe record creation with the same validation/dry-run semantics as the CLI.
3. Route every tool through existing domain functions; do not create a second data model or ranking path.
4. Test protocol schemas, root scoping, missing archive behavior, malformed arguments, JSON serialization, and mutation safety without network access.
5. Document client configuration for harnesses where direct CLI invocation is awkward.
6. Commit: `feat: add optional MCP integration`.

**Acceptance:** `pipx install '<distribution>[mcp]'` starts a stdio server; CLI-only installation remains unchanged; MCP and CLI return equivalent search results for the same archive/query.

## Phase 4 — make the promise visible and reproducible

### Task 10: Build a synthetic sample project and executable demo

**Files:**
- Create: `examples/sample-project/` with code, 6–10 records, an eval set, lifecycle example, and optional replay trace
- Create: `examples/run_demo.py`
- Create: `tests/test_demo.py`
- Modify: example README and root README

**Steps:**

1. Design one consequential but fictional failure: an agent simplifies a configuration loader and breaks replacement semantics.
2. Make the demo show: incorrect assumption → initial miss or absent constraint → reviewed record → fresh-session search → corrected implementation decision → readable Markdown source.
3. Run entirely in a temporary copy; never write to HOME, the repository, or a user archive.
4. Add deterministic assertions for output, returned record, offline execution, runtime under two minutes, and cleanup.
5. Keep replay optional and second: ship one completed trace that demonstrates prefix-only offline comparison.
6. Commit: `docs: add reproducible sample project`.

**Acceptance:** one documented command runs from a clean checkout and proves the before/after value without setup, credentials, or private data.

### Task 11: Create a reproducible public benchmark

**Files:**
- Create: `benchmarks/synthetic-v1/{records,queries.json,judgments.json,LICENSE}`
- Create: `benchmarks/run.py`, `benchmarks/results/v1.json`, `benchmarks/README.md`
- Create: `tests/test_benchmark.py`

**Steps:**

1. Freeze and license a synthetic corpus and relevance judgments before running interventions.
2. Include difficult vocabulary mismatches, stale/superseded records, section matches, identifier expansions, and genuine no-answer queries.
3. Compare a declared whole-record FTS baseline with Lore’s indexed/ranked variants and ablations.
4. Report recall@1/3/5, MRR, zero-result rate, returned-token budget, p50/p95 latency, corpus/query counts, platform, Python/Lore version, and commit.
5. Keep negative results and limitations in the generated report; distinguish this benchmark from the existing single-archive field snapshot and biased regression eval.
6. Make `python benchmarks/run.py --verify benchmarks/results/v1.json` fail when checked-in claims drift beyond a declared tolerance.
7. Commit: `bench: add reproducible synthetic retrieval benchmark`.

**Acceptance:** anyone can reproduce the README table offline from public inputs with one command; field telemetry is never presented as a general benchmark.

### Task 12: Record the 45–60 second terminal demonstration

**Files:**
- Create: `demo/demo.tape`, `demo/README.md`, `docs/img/demo.gif` (or accessible MP4/WebM plus poster image)
- Modify: `README.md`

**Steps:**

1. Drive the recording from `examples/run_demo.py`; do not hand-type a path that can drift from the tested scenario.
2. Show exactly five beats: repeated wrong assumption, record the constraint, start a fresh shell/session, search Lore, avoid the mistake and open the Markdown.
3. Keep it 45–60 seconds, readable at README width, captioned or accompanied by a transcript, and optimized for repository size.
4. Regenerate in CI or document a checksum-backed reproducible command; verify the link on GitHub and PyPI rendering.
5. Commit: `docs: add terminal product demonstration`.

**Acceptance:** a viewer understands the problem and payoff without reading prose; the underlying script is tested and deterministic.

### Task 13: Rewrite and audit the README around the core product

**Files:**
- Modify: `README.md`
- Create: `docs/advanced-replay.md`, `docs/evidence.md`
- Modify: `INSTALL.md`, `METRICS.md`, `tools/lore/CLI_SPEC.md`, repository map

**Steps:**

1. Use this order: one-sentence problem; demo; one-command pipx install; three differences; realistic before/after; evidence; integrations; advanced replay teaser; documentation links.
2. Open with the review’s scar-tissue framing and keep “Your code remembers what survived. Lore remembers why.”
3. Put `lore search "why can't we simplify this config loader?"` in the first workflow example.
4. Move the full Dream-RSI/replay explanation and commands to `docs/advanced-replay.md`; label it experimental, offline, deterministic, prefix-only, and never autonomously promoted.
5. Add a real CI badge only after the workflow is green. Avoid hard-coded test counts unless generated at release time.
6. Audit every command, path, metric, version, diagram, safety promise, and limitation against a clean installed wheel. Correct the currently inaccurate repository tree rather than creating empty paths to satisfy it.
7. Preserve only diagrams that materially explain mechanism; the GIF is the primary visual proof. Add alt text and keep source files for maintained diagrams.
8. Run Markdown link checking, package README rendering (`twine check`), command smoke tests, and the clean-checkout verifier.
9. Commit: `docs: focus README on durable engineering memory`.

**Acceptance:** a new user reaches a successful search from the first screen, replay no longer competes with the primary workflow, every claim has a test/source, and the README still has a distinct human voice.

## Phase 5 — establish public trust

### Task 14: Add CI, packaging checks, and release automation

**Files:**
- Create: `.github/workflows/ci.yml`, `.github/workflows/release.yml`
- Modify: `tools/verify.py`, `README.md`

**Steps:**

1. Add a matrix for Python 3.10, 3.11, 3.12, and 3.13 on `ubuntu-latest`, `macos-latest`, and `windows-latest`; use `fail-fast: false`.
2. Run install-from-wheel tests, the full verifier, CLI selftest, demo test, benchmark verification, Markdown links, and `twine check`.
3. Add a separate minimal-dependency/offline smoke job and protect `main` with required checks.
4. Add a tag-triggered workflow that builds once, verifies artifacts, records SHA-256 hashes, uploads wheel/sdist to the GitHub release, and uses trusted publishing for PyPI only after the package name/account is ready.
5. Pin actions to reviewed major versions or immutable SHAs according to the project’s supply-chain policy.
6. Commit: `ci: verify supported platforms and release artifacts`.

**Acceptance:** all 12 OS/Python combinations pass on the same commit; artifacts installed in CI match uploaded artifacts; the README badge links to that commit’s workflow.

### Task 15: Add governance and contribution surfaces

**Files:**
- Create: `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`, `CODE_OF_CONDUCT.md`, `SUPPORT.md`, `GOVERNANCE.md`
- Create: `.github/ISSUE_TEMPLATE/bug.yml`, `feature.yml`, `config.yml`, `PULL_REQUEST_TEMPLATE.md`, `CODEOWNERS`

**Steps:**

1. Document environment setup, architecture map, focused/full tests, commit/PR expectations, compatibility policy, and how to add a schema migration.
2. Publish a private security-reporting route, supported versions, response expectations, and a clear warning never to put archive contents in public issues.
3. Start a Keep-a-Changelog-style file with `[Unreleased]` and the first beta; derive release notes from it.
4. Use issue forms that request minimal reproducible examples while explicitly prohibiting proprietary records, queries, credentials, or unredacted metric exports.
5. Adopt an established code of conduct and list enforcement contacts.
6. Add an honest single-maintainer governance document covering decision authority, succession, compatibility/deprecation, and release approval; route Q&A to Discussions, bugs to Issues, and vulnerabilities to the private security channel.
7. Commit: `docs: add open-source governance`.

**Acceptance:** GitHub’s community profile recognizes all files; security disclosures have a non-public path; a first-time contributor can run and test the project without tribal knowledge.

### Task 16: Publish a real beta release

**Files:**
- Modify: version source, `CHANGELOG.md`, `README.md`
- Create: `docs/releases/<version>.md`, annotated Git tag, GitHub release, wheel, sdist, checksums

**Steps:**

1. Choose an honest alpha/beta version after naming; do not reuse the README’s current `0.5.0` claim without reconciling package/version history.
2. Run the clean-checkout verifier, CI matrix, demo, benchmark verification, history scan, artifact install tests, and `twine check` against the release commit.
3. Create an annotated tag; generate release notes from the changelog; attach reproducible artifacts and checksums.
4. Install the uploaded artifact via pipx on all three OS families and execute init/setup/search/selftest.
5. Document rollback/yank steps before publishing.
6. Commit the release metadata: `chore: prepare <version> beta release`.

**Acceptance:** the tag, GitHub release, package metadata, CLI version, changelog, artifacts, and README agree exactly; a release can be rebuilt from the tag.

## Phase 6 — prove usability before publicity

### Task 17: Run the private beta

**Files:**
- Create: `docs/beta/protocol.md`, `docs/beta/feedback-template.md`
- Keep individual/private results outside the public repository; publish only consented aggregates

**Steps:**

1. Recruit 5–10 developers across Claude Code, Codex, Cursor, and OpenCode; require at least three external to the project before public release.
2. Measure: time to first successful search, installation failures, searches/week, miss rate, whether retrieval changed an implementation decision, and stale/incorrect records.
3. Ask every tester for one sentence about a prevented mistake and explicit permission before attribution.
4. Triage failures by launch severity; close all install/data-loss/privacy blockers and rerun affected harness tests.
5. Publish anonymized aggregate methodology and results, including dropouts and negative feedback.

**Acceptance:** three external users complete install → setup → search on real repositories; median time-to-first-search and every failure are recorded; no unresolved P0 issue remains.

### Task 18: Configure repository discoverability

**External settings plus files:**
- GitHub About description, homepage, topics, Discussions, visibility, branch protection
- Modify: `README.md` support links

**Steps:**

1. Set the final description/homepage and topics: `ai-agents`, `coding-agents`, `agent-memory`, `developer-tools`, `sqlite`, `fts5`, `local-first`, `claude-code`, `codex`, and `markdown` (within GitHub’s limit).
2. Enable Issues and security reporting before visibility changes; enable Discussions only when the maintainer is ready to answer first users.
3. Upload a clear social-preview image; keep the homepage blank until there is a durable destination worth maintaining.
4. Make the repository public only after the launch-gate checklist is signed.
5. Immediately verify anonymous clone, release download, docs/demo rendering, package install, and security/community links.

**Acceptance:** an unauthenticated user can discover, install, verify, report a bug, and find support without private links or owner intervention.

## Phase 7 — launch without burning trust

### Task 19: Prepare and run Show HN

**Files:**
- Create: `docs/launch/show-hn.md`

**Steps:**

1. Use the title: “Show HN: <Final Name>, Git-tracked engineering memory for coding agents.”
2. Lead with the repeated-expensive-mistake story, then the narrow positioning, local/Markdown/FTS5 mechanism, demo/repository link, and an honest request for feedback.
3. Ensure users can try it immediately without signup, waitlist, or private access; Hacker News requires a Show HN to be something people can run or interact with.
4. Be present to answer technical questions. Do not ask colleagues or communities to upvote; coordinated voting is prohibited.
5. Capture questions and failures as issues, not defensive README expansion.

**Acceptance:** the released artifact and demo work anonymously when the post is submitted; maintainer coverage exists for the discussion window.

### Task 20: Stage audience-specific Reddit posts

**Files:**
- Create: `docs/launch/reddit.md`

**Steps:**

1. Re-check each subreddit’s current self-promotion and posting rules immediately before posting; record the date and permitted format.
2. Write distinct posts for: `r/AI_Agents` (continuity/architecture), `r/LocalLLaMA` (fully local/no model or API), `r/ClaudeAI` (Claude Code workflow), `r/cursor` (Cursor setup/demo), `r/opensource` (MIT/design/contribution), and `r/Python` (packaging/SQLite FTS5 lessons).
3. Space posts out and participate in each community; never paste the same launch copy everywhere.
4. Prefer the title “I built a local Markdown memory system because my coding agents kept repeating expensive mistakes.”
5. End with the concrete request: five people willing to try an existing repository and report failed searches.

**Acceptance:** every post is rule-compliant on posting day, technically relevant to its community, and links to a runnable release rather than a signup page.

## Coverage of every review item

| Review item | Covered by |
|---|---|
| Hacker News, not HackerRank; Show HN must be runnable; no coordinated votes | Task 19 |
| Narrow institutional-memory positioning; competitor differentiation; keep the slogan | Task 2, Task 13 |
| Replay is advanced rather than a second primary product | Tasks 2, 10, 13 |
| PyPI/search/name collision and trademark/availability decision | Task 1 |
| pipx install, `lore init`, easy setup | Tasks 5, 6, 8 |
| CI on Python 3.10–3.13 and Ubuntu/macOS/Windows; real badge | Task 14 |
| Tag, release, notes, changelog, reproducible artifacts, beta label | Tasks 15–16 |
| CONTRIBUTING, SECURITY, CHANGELOG, issue templates, code of conduct | Task 15 |
| Full-history secret/privacy scan and synthetic signing-key example | Task 3 |
| 45–60 second terminal demonstration | Tasks 10, 12 |
| Claude, Codex, Cursor, OpenCode setup | Task 8 |
| Optional MCP server | Task 9 |
| Complete sample project | Task 10 |
| Move internal plans and `implement/` artifacts | Task 4 |
| Split the 3,622+ line monolith | Task 7 |
| GitHub topics, homepage, Discussions | Task 18 |
| Reproducible synthetic benchmark; honest one-archive evidence limits | Task 11, Task 13 |
| README’s exact new order, opening, search example, diagrams/soul | Task 13 |
| Private beta across four harnesses and all requested metrics/testimonials | Task 17 |
| Public-release gates and at least three external testers | Tasks 3, 14–18 |
| Tailored Reddit rollout and current-rule checks | Task 20 |
| Weak trust/usability signals and roughly 50% readiness | Gates plus Phases 2–6 |

## Final verification checklist

Run from the release tag in a clean checkout:

```bash
python3 -B tools/verify.py --clean-checkout
python -m build
python -m twine check dist/*
python benchmarks/run.py --verify benchmarks/results/v1.json
python examples/run_demo.py --verify
```

Then install the built wheel—not the source tree—with pipx on Ubuntu, macOS, and Windows and verify:

```bash
lore --version
lore init <temporary-path>
lore setup <harness> --dry-run
lore search "why can't we simplify this config loader?"
lore selftest
```

No visibility change or launch post occurs until the named owner signs every gate with links to the passing run, artifact hashes, audit report, beta summary, and release.
