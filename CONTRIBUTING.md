# Contributing to Lore

Thanks for helping make durable engineering knowledge easier to preserve and
retrieve. Lore is a local-first tool: readable Markdown is canonical and the
local SQLite index is disposable. Changes should protect that promise.

## Before you begin

- Read the [README](README.md) and relevant documentation before proposing a
  change.
- Search open issues and pull requests to avoid duplicate work.
- For substantial changes, open an issue or discussion first so maintainers and
  contributors can agree on the problem and scope.
- Follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Development workflow

1. Fork the repository and create a focused branch from the default branch.
2. Keep each pull request small and directed at one user-visible problem.
3. Add or update tests for behavior changes, including failure paths where
   practical.
4. Run the relevant checks documented in the repository before opening the PR.
5. Update user-facing documentation, CLI help, and examples when behavior or
   terminology changes.

Do not include secrets, customer data, credentials, private repository paths,
or production-derived examples in issues, commits, tests, fixtures, or docs.
Use clearly marked synthetic data instead.

## What makes a good contribution

Lore values changes that are:

- **Local-first:** no account, daemon, telemetry, or network dependency is
  required for core use.
- **Safe:** Markdown remains canonical; destructive operations are explicit,
  validated, and recoverable when possible.
- **Explainable:** command output, schemas, and failure messages help people
  understand what happened.
- **Compatible:** existing archives and automation keep working, or a migration
  is documented and tested.
- **Measured:** retrieval, metrics, and replay claims include reproducible
  evidence rather than implied guarantees.

## Pull request expectations

Please describe the problem, the chosen approach, alternatives considered when
relevant, verification performed, and any remaining risks. A maintainer may
ask for a smaller scope, additional tests, a migration plan, or documentation
changes before merging.

By contributing, you agree that your contributions may be distributed under the
repository's [MIT License](LICENSE).

## Getting help

Use the routes in [SUPPORT.md](SUPPORT.md) for questions, bug reports, feature
ideas, and security reports.
