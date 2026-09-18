"""Oldhand: validation layer. Split out of the former single-file CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import (
    DURABILITY,
    ENTRY_TYPES,
    EVIDENCE,
    IMPORTANCE,
    RELATION_TYPES,
    RETIRED_STATUSES,
    RISKS,
    SCOPES,
    STATUSES,
)
from .workspace import discover_collections, display_path
from .records import parse_record, record_files


def validate_records(root: Path) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Return (valid records, errors, warnings).

    Every error names the file it came from, so a fail-open rebuild can skip
    exactly that record and keep the rest of the archive available.
    """
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []
    seen_ids: dict[str, list[Path]] = {}
    rejected: set[Path] = set()

    def reject(path: Path, message: str) -> None:
        errors.append(f"{display_path(root, path)}: {message}")
        rejected.add(path)

    for collection_root in discover_collections(root):
        for p in record_files(collection_root):
            try:
                r = parse_record(p)
            except Exception as e:
                reject(p, str(e))
                continue

            meta = r["meta"]
            required = [
                "schema_version", "id", "type", "status", "importance",
                "scope", "risk", "durability", "evidence",
                "created_at", "updated_at",
            ]
            for field in required:
                if field not in meta or meta[field] in (None, ""):
                    reject(p, f"missing required field '{field}'")

            version = meta.get("schema_version")
            if type(version) is not int or version != 1:
                reject(p, "schema_version must be the integer 1")

            checks = [
                ("type", ENTRY_TYPES),
                ("status", STATUSES),
                ("importance", IMPORTANCE),
                ("scope", SCOPES),
                ("risk", RISKS),
                ("durability", DURABILITY),
                ("evidence", EVIDENCE),
            ]
            for field, allowed in checks:
                val = str(meta.get(field, ""))
                if val and val not in allowed:
                    reject(p, f"invalid {field} '{val}'")

            rid = str(meta.get("id", ""))
            if rid:
                seen_ids.setdefault(rid, []).append(p)

            if not r["summary"]:
                reject(p, "missing or empty '## Summary' section")
            if "knowledge" not in r["sections"]:
                reject(p, "missing '## Knowledge' section")

            for rtype, targets in r["relations"].items():
                if rtype not in RELATION_TYPES:
                    reject(p, f"invalid relation type '{rtype}'")
                if rid and rid in targets:
                    reject(p, f"relation '{rtype}' targets its own id '{rid}'")

            records.append({"path": p, "collection_root": collection_root, **r})

    for rid, paths in seen_ids.items():
        if len(paths) > 1:
            named = ", ".join(display_path(root, path) for path in paths)
            for path in paths:
                reject(path, f"duplicate id '{rid}' also in {named}")

    records_by_path = {r["path"]: r for r in records}

    for r in records:
        rid = str(r["meta"].get("id", ""))
        for rtype, targets in r["relations"].items():
            for target in targets:
                if target not in seen_ids:
                    reject(r["path"], f"relation '{rtype}' targets unknown id '{target}'")
                    continue
                # Supersession is only real once the target is actually retired.
                # Without this check the replaced record keeps outranking the
                # record that replaced it, and nothing ever says so.
                if rtype == "supersedes":
                    target_status = str(
                        records_by_path[seen_ids[target][0]]["meta"].get("status", ""))
                    if target_status not in RETIRED_STATUSES:
                        reject(
                            r["path"],
                            f"supersedes '{target}' but that record's status is "
                            f"'{target_status}'; set it to 'superseded' (or 'deprecated')",
                        )

        if str(r["meta"].get("status", "")) == "superseded" and rid:
            claimed_by = [o for o in records if rid in o["relations"].get("supersedes", [])]
            if not claimed_by:
                warnings.append(
                    f"{display_path(root, r['path'])}: status is 'superseded' but no record "
                    f"declares 'supersedes: {rid}'"
                )

    duplicate_ids = {rid for rid, paths in seen_ids.items() if len(paths) > 1}
    valid = [r for r in records
             if r["path"] not in rejected and str(r["meta"].get("id", "")) not in duplicate_ids]
    return valid, errors, warnings
