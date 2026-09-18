# Changelog

All notable user-facing changes to Lore will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and Lore uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html) for
released versions.

## [0.6.0b1] - 2026-09-19

First release under the name **Oldhand**, and the first installable one.

### Changed - renamed from Lore

The project was called Lore. Every name that kept it collided on PyPI:
`lore` is an unrelated machine-learning framework, `lore-memory` is a direct
competitor with near-identical messaging, and `lore-cli` is another
developer tool. `pip install lore` could never have been offered, and
search would have sent users to a competitor.

- Distribution, console command and import package are all `oldhand`.
- `OLDHAND_ROOT` replaces `LORE_ROOT`. `LORE_ROOT` is still read, so existing
  archives keep working; `OLDHAND_ROOT` wins when both are set.
- The index directory is now `.oldhand/` holding `oldhand.db`. It is derived
  state: delete the old `.lore/` directory, and the next command rebuilds.
- Metrics snapshots and index metadata record `oldhand_version`. The former
  `lore_version` key is still accepted, so metrics history recorded before
  the rename is not retroactively treated as malformed.

### Added

- Standard Python packaging. `pipx install oldhand` or `pip install oldhand`
  replaces cloning the repository and running a script from inside it.
- A CI job that builds the wheel and sdist, installs the wheel into a clean
  virtual environment, runs the console script, and publishes checksums.
- Community, security and contribution guidance for the public launch.
- An evidence guide separating field observations, controlled interventions
  and synthetic regression results.
- A versioned, reproducible synthetic retrieval benchmark with a checked-in
  baseline.
- `LORE_DEBUG`/`OLDHAND_DEBUG` surfaces metrics-recording failures that were
  previously swallowed in silence.

### Fixed

- The `path` field in JSON output was rendered with the platform separator,
  so it came back with backslashes on Windows. It is now POSIX everywhere.
- Daily metrics were written from an `atexit` handler, which depended on
  interpreter finalization and did not run reliably on Python 3.13. Recording
  is now deterministic, under `try`/`finally`.
- `metrics --export` rejected any PEP 440 pre-release version string.

### Project layout

The CLI moved from `tools/lore/lore.py` to `src/oldhand/cli.py`, and tests
moved to `tests/`. Behaviour is unchanged; 187 tests pass on Python
3.10-3.13 on Linux and macOS.

## [Unreleased]

### Added

- Community, security, and contribution guidance for the public launch.
- An evidence guide that keeps field observations, controlled interventions,
  and synthetic regression results separate.
- A versioned, reproducible synthetic retrieval benchmark and checked-in
  baseline result artifact.

### Changed

- Release documentation now distinguishes local archive evidence from
  generalizable product claims.

### Release checklist

Before cutting the next public release:

- [ ] Choose and document the canonical public package and project identity.
- [ ] Run the full test suite on supported Python versions and operating
  systems in CI.
- [ ] Run `python -B tools/run_synthetic_benchmark.py --verify` and review any
  baseline change in `benchmarks/synthetic/results.json`.
- [ ] Run the repository-history and example-data audit; resolve or explicitly
  accept every finding before changing repository visibility.
- [ ] Verify package build artifacts in a clean environment and record their
  checksums.
- [ ] Review this file, assign the release version/date, create an annotated
  tag, and attach release notes plus package artifacts to the GitHub release.

### Known limitations

- Published field measurements and controlled interventions currently come
  from one archive; they are not independent validation.
- The synthetic benchmark is a deterministic regression fixture, not a
  realistic adoption or retrieval-quality benchmark.
- Replay evaluates already-recorded discovery traces and never executes an
  agent or predicts unseen outcomes.
- Windows is not supported. The release CI matrix now measures it on an
  informational `windows-preview` job, which fails: `show --json` produces no
  stdout under the end-to-end harness, and installer symlink handling is
  unverified. Linux and macOS are verified on Python 3.10-3.13.
- Package-installation ergonomics must be verified from a clean environment
  before being claimed as supported.
- Lore is local software, not an access-control, backup, secret-management, or
  compliance system.

## Historical releases

Historical tags predate this changelog. Do not infer that a release exists
from a README or source version string; the next public release will receive
an explicit dated section only when its annotated tag and GitHub Release are
published.

[Unreleased]: https://github.com/IotA-asce/lore/compare/v0.4.3...HEAD
