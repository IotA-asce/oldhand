# Changelog

All notable user-facing changes to Lore will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and Lore uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html) for
released versions.

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
- Native Windows support and package-installation ergonomics must be verified
  by the release CI matrix before being claimed as supported.
- Lore is local software, not an access-control, backup, secret-management, or
  compliance system.

## Historical releases

Historical tags predate this changelog. Do not infer that a release exists
from a README or source version string; the next public release will receive
an explicit dated section only when its annotated tag and GitHub Release are
published.

[Unreleased]: https://github.com/IotA-asce/lore/compare/v0.4.3...HEAD
