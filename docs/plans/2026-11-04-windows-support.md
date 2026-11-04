# Windows Support Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Support native Windows installations with verified CLI, Obsidian, installer, and distribution behavior.

**Architecture:** Keep the existing platform-neutral Python package. Repair Windows launcher generation and explicit UTF-8 boundaries; make test fixtures and benchmark checks independent of native line endings and path aliases. Promote Windows to the required CI matrix and verify the installed wheel through a portable distribution smoke script.

**Tech Stack:** Python 3.10–3.13, pathlib/subprocess, Windows cmd/PowerShell, GitHub Actions, Hatchling/PyPI.

---

1. Inspect real Windows failures before changes. Baseline: both preview jobs fail with 8 assertion failures and 4 errors, including CRLF launcher ownership, Unicode decoding, profile fixture assumptions, and a CRLF-dependent benchmark digest.
2. Fix `tools/install.py` Windows launcher line endings, batch environment quoting, local environment scope and UTF-8 subprocess decoding. Add focused regression tests and a native Windows launcher integration test. Keep symlink ownership protection; do not remove checks to green the build.
3. Fix encoding and path/line-ending assumptions in tests and use a canonical text digest for the synthetic Markdown corpus. Existing benchmark semantics and results must remain unchanged.
4. Add `tools/check_distribution.py` to install the wheel in a clean venv and exercise its console entry point, Unicode records, search/show JSON, and Obsidian links. Run this on Linux, macOS, and Windows in CI. Promote Windows Python 3.10–3.13 to required verification jobs.
5. Validate locally, commit and push the feature branch for native Windows CI. Investigate any remaining failures there before merging. Update platform metadata and Windows PowerShell/install documentation only against passing evidence.
6. Prepare the next beta, merge and push after all required checks pass, publish it through Trusted Publishing, and verify the published artifact and metadata. Preserve prior release tags.

No Windows host is available locally. Native Windows claims require real hosted Windows jobs, not mocked platform flags. POSIX shell integration tests remain platform-scoped; native Windows integration receives its own coverage. No private archive is modified.

First hosted run: native wheel/console/Unicode/Obsidian checks passed on all
three platforms. The full Windows suite reduced to one failing demo test:
the demo itself still emitted ANSI bytes to an explicitly UTF-8 reader.
The test now forces cp1252 even on Unix to reproduce that failure, and the
demo configures its output as UTF-8. Native launcher and all other Windows
tests passed. Symlink ownership tests now run on Windows when the OS grants
the necessary privilege; only the OS privilege error is a capability skip.

The local 213-test suite and ranking selftest pass; the next candidate is
0.6.0b3. Wheel/sdist pass `twine check`. Support documentation and metadata are
prepared on the feature branch and must not be merged/released until the
updated native CI matrix passes.
