"""Reconciliation decisions that survive re-migration.

A migration is re-run: weekly during a trial, and again whenever the source
archive changes. Anything decided *about* the migrated records, rather than
written in the sources, is destroyed each time. That includes every answer to
`lore conflicts`: this record supersedes that one, these two are related, this
one is retired.

Losing those silently is worse than never recording them, because the report
comes back clean-looking the first time and full again the next, and nobody
can tell reconsidered from reverted.

So resolutions live in `reconcile.jsonl` at the archive root, applied by every
migration. One JSON object per line, keyed by record id:

    {"id": "lore_x", "relations": {"related_to": ["lore_y"]}}
    {"id": "lore_x", "status": "superseded", "note": "replaced by lore_y"}

`note` is for whoever reads the file later and is not written into the record.
"""
from __future__ import annotations

import json
from pathlib import Path


def load_overrides(archive_root: Path) -> dict[str, dict]:
    """Read reconcile.jsonl from the archive root. Absent means no overrides."""
    path = archive_root / "reconcile.jsonl"
    if not path.exists():
        return {}
    out: dict[str, dict] = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            entry = json.loads(line)
        except ValueError as exc:
            raise SystemExit(f"{path}:{n}: not valid JSON ({exc})")
        rid = entry.get("id")
        if not rid:
            raise SystemExit(f"{path}:{n}: every line needs an \"id\"")
        merged = out.setdefault(rid, {})
        for key, value in entry.items():
            if key in ("id", "note"):
                continue
            if key == "relations":
                rel = merged.setdefault("relations", {})
                for rtype, targets in (value or {}).items():
                    existing = rel.setdefault(rtype, [])
                    for target in targets:
                        if target not in existing:
                            existing.append(target)
            else:
                merged[key] = value
    return out


def apply_status(record_id: str, status: str, overrides: dict[str, dict]) -> str:
    return str(overrides.get(record_id, {}).get("status", status))


def extra_relations(record_id: str, overrides: dict[str, dict]) -> dict[str, list[str]]:
    return dict(overrides.get(record_id, {}).get("relations", {}))


def render_relations(relations: dict[str, list[str]]) -> list[str]:
    """Frontmatter lines for a relations mapping, or the empty form."""
    if not relations:
        return ["relations: {}"]
    lines = ["relations:"]
    for rtype, targets in relations.items():
        if not targets:
            continue
        lines.append(f"  {rtype}:")
        lines.extend(f"    - {t}" for t in targets)
    return lines if len(lines) > 1 else ["relations: {}"]
