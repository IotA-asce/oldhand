"""Oldhand: authoring layer. Split out of the former single-file CLI."""

from __future__ import annotations

from pathlib import Path
import json
import sys

from .indexing import rebuild


def init_archive(root: Path, json_output: bool = False) -> int:
    root = root.resolve()
    memory = root / "memory"
    if memory.exists():
        print(f"Refusing to overwrite existing archive: {memory}", file=sys.stderr)
        return 1
    memory.mkdir(parents=True)
    (memory / "README.md").write_text(
        "# Memory\n\n"
        "Canonical Oldhand records live below this directory. Create one with:\n\n"
        "```bash\n"
        "oldhand new --title \"...\" --type lesson --importance normal\n"
        "```\n",
        encoding="utf-8",
    )
    rebuild(root, strict=True, quiet=True)
    if json_output:
        print(json.dumps({
            "created": True, "root": str(root),
            "memory": str(memory), "records": 0,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"Initialized Oldhand archive at {root}")
        print("Next: oldhand new --title \"...\" --type lesson --importance normal")
    return 0
