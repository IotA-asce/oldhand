# PyPI Link Fix and Beta Release Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Publish Oldhand 0.6.0b2 with native Obsidian support and working links on its PyPI page.

**Architecture:** Keep the existing GitHub repository, package name, and Trusted Publishing workflow. Make README documentation links and images absolute, verify repository targets, update the package version/release notes, and publish a new immutable distribution.

**Tech Stack:** Python packaging with Hatchling, GitHub Actions OIDC, PyPI, Markdown.

---

1. On `bugfix/pypi-links-release`, replace relative README links with absolute links to existing GitHub documents and raw assets. Add direct documentation/Obsidian project links in package metadata. Remove source-only wording for the Obsidian feature.
2. Add a focused regression test for portable README links and repository target existence. Set version to `0.6.0b2`, update install guidance and dated changelog.
3. Run the full verifier, synthetic benchmark, build, `twine check`, packaged-metadata/link checks, and a clean wheel install with an Obsidian smoke test.
4. Commit, fast-forward merge to main, push, tag `v0.6.0b2`, and create its GitHub prerelease with exact validated artifacts and release notes. Use the configured publish workflow and inspect its result; dispatch it against the tag if release-triggered execution is absent.
5. Verify PyPI's version, links, artifact hashes/provenance and installation of the published version. Update workspace project tracking.

Constraints: no overwrite of old PyPI files, no API-token disclosure, no unrelated source changes, no changes to private archives. Native Obsidian UI testing is unavailable locally; automated source/CLI integration tests cover the feature.

Pre-publication verification: 210 tests and ranking selftests pass on Python 3.10
and 3.14; the retrieval benchmark is unchanged. Wheel and sdist build and pass
`twine check`. All 36 README link targets are absolute, local repository targets
exist, and all 25 owned remote document/asset destinations return HTTP 200.
The wheel metadata contains the new documentation links and version, and an
isolated Python 3.12 install passes version/init/Obsidian/authoring/search checks.
