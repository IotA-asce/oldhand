#!/usr/bin/env python3
"""Re-run every migration into a Lore archive, then rebuild the index.

One command because a partial re-sync is worse than none. The archive here has
four collections fed by four different source directories, and the obvious
failure is refreshing the one you remember and leaving three stale. Nothing
reports that: search keeps working, validation passes, and the answers quietly
describe last week.

Reads a `sources.jsonl` manifest beside the archive so the set of collections
lives with the archive rather than in a command someone has to retype:

    {"tool": "claude_memory", "src": "...\\\\memory"}
    {"tool": "repo_memory", "src": "...\\\\my-service\\\\memory", "collection": "svc"}

Idempotent. Sources are only ever read. Anything recorded in
`reconcile.jsonl` is reapplied by each migration, so decisions survive.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LORE_CLI = HERE.parent / "lore" / "lore.py"
TOOLS = {
    "claude_memory": HERE / "from_claude_memory.py",
    "repo_memory": HERE / "from_repo_memory.py",
}


def fingerprint(root: Path) -> str:
    """Hash of every record file, to show whether anything actually changed."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("memory/**/*.md")):
        h.update(p.relative_to(root).as_posix().encode("utf-8"))
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


def main() -> int:
    archive = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    manifest = archive / "sources.jsonl"
    if not manifest.exists():
        print(f"No manifest at {manifest}.", file=sys.stderr)
        print("One JSON object per line: {\"tool\": ..., \"src\": ..., \"collection\": ...}",
              file=sys.stderr)
        return 1

    entries = []
    for n, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            entries.append(json.loads(line))
        except ValueError as exc:
            print(f"{manifest}:{n}: {exc}", file=sys.stderr)
            return 1

    before = fingerprint(archive)
    failures = []

    for e in entries:
        tool = TOOLS.get(e.get("tool", ""))
        src = Path(e["src"])
        coll = e.get("collection")
        if tool is None:
            print(f"  unknown tool {e.get('tool')!r}", file=sys.stderr)
            failures.append(e)
            continue
        if not src.is_dir():
            print(f"  MISSING SOURCE, collection left as it was: {src}", file=sys.stderr)
            failures.append(e)
            continue
        target = archive / coll if coll else archive
        cmd = [sys.executable, str(tool), str(src), str(target)]
        if coll:
            cmd.append(coll)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  FAILED {coll or 'workspace'}: {r.stderr.strip()[:200]}", file=sys.stderr)
            failures.append(e)
            continue
        last = [l for l in r.stdout.splitlines() if l.strip()]
        print(f"  {coll or 'workspace':<18} {last[-3] if len(last) > 2 else (last[0] if last else 'ok')}"
              if coll else f"  {'workspace':<18} {last[0] if last else 'ok'}")

    after = fingerprint(archive)
    print()
    print("no record changed" if before == after
          else f"records changed: {before} -> {after}")

    rebuild = subprocess.run([sys.executable, str(LORE_CLI), "--root", str(archive), "rebuild"],
                             capture_output=True, text=True)
    print((rebuild.stdout or rebuild.stderr).strip().splitlines()[-1])
    validate = subprocess.run([sys.executable, str(LORE_CLI), "--root", str(archive), "validate"],
                              capture_output=True, text=True)
    print((validate.stdout or validate.stderr).strip().splitlines()[-1])

    if failures:
        print(f"\n{len(failures)} source(s) did not sync. The collections they feed still hold",
              file=sys.stderr)
        print("their previous contents, which is stale, not empty. Fix before trusting a search.",
              file=sys.stderr)
        return 1
    return 0 if validate.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
