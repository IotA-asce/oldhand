#!/usr/bin/env python3
"""Run Lore's fully local, synthetic before-and-after demonstration.

The script copies ``sample-project`` into a newly created temporary directory.
All indexing, retrieval logging, and generated files stay there; it never
writes to this repository, a caller's current directory, or the home
directory.  It needs only Python and Lore's normal PyYAML dependency.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


EXAMPLES = Path(__file__).resolve().parent
SOURCE_PROJECT = EXAMPLES / "sample-project"
LORE_CLI = EXAMPLES.parent / "tools" / "lore" / "lore.py"
RECORD_ID = "synthetic_environment_config_replaces_defaults"


def run_lore(workspace: Path, *arguments: str) -> str:
    """Execute the local CLI against the temporary workspace and return stdout."""
    completed = subprocess.run(
        [sys.executable, str(LORE_CLI), "--root", str(workspace), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def display_value(config: dict[str, object], key: str) -> str:
    """Make a missing setting explicit, rather than silently printing nothing."""
    return str(config.get(key, "<missing: staging must declare it explicitly>"))


def main() -> int:
    if not SOURCE_PROJECT.is_dir() or not LORE_CLI.is_file():
        raise RuntimeError("run_demo.py must run from Lore's checked-out examples directory")

    with tempfile.TemporaryDirectory(prefix="lore-synthetic-demo-") as temporary:
        workspace = Path(temporary) / "sample-project"
        shutil.copytree(SOURCE_PROJECT, workspace)

        sys.path.insert(0, str(workspace))
        from config_loader import load_config  # pylint: disable=import-outside-toplevel

        defaults = load_config(workspace / "config")
        staging = load_config(workspace / "config", "staging")
        search = json.loads(run_lore(
            workspace,
            "search",
            "why can't we simplify this config loader",
            "--json",
        ))
        record = json.loads(run_lore(workspace, "show", RECORD_ID, "--json"))

        print("Lore synthetic demo — no network, account, model, or real project data")
        print()
        print("Before: no environment file selected")
        print(f"  DATABASE_URL = {display_value(defaults, 'DATABASE_URL')}")
        print()
        print("After: synthetic staging file selected")
        print(f"  DATABASE_URL = {display_value(staging, 'DATABASE_URL')}")
        print("  Interpretation: add DATABASE_URL to staging; do not merge defaults.")
        print()
        print('Lore search: why can\'t we simplify this config loader?')
        print(f"  Retrieved: {search['results'][0]['id']}")
        print(f"  Summary: {search['results'][0]['summary']}")
        print()
        print(f"Lore show: {RECORD_ID}")
        print(f"  Title: {record['title']}")
        print(f"  Evidence: {record['evidence']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
