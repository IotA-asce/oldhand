"""Oldhand: harness layer. Split out of the former single-file CLI."""

from __future__ import annotations

from . import experience
from datetime import datetime
from pathlib import Path
from typing import Any
import argparse
import difflib
import hashlib
import json
import os
import re
import sys
import tempfile

from .constants import (
    DIRECT_STATUSES,
    FRONTMATTER_RE,
    RECORD_ID_RE,
    RETIRED_STATUSES,
    SETUP_END,
    SETUP_GUIDANCE,
    SETUP_START,
    SLUG_STRIP_RE,
    TYPE_DIRS,
    yaml,
)
from .workspace import _atomic_write, collection_name, discover_collections, display_path
from .records import record_files
from .validation import validate_records
from .indexing import rebuild


def _setup_target(root: Path, harness: str) -> tuple[Path, str, bool]:
    """Return target, file prefix, and whether an existing file is required."""
    if harness == "claude":
        return root / ".claude" / "rules" / "oldhand.md", "", False
    if harness == "cursor":
        return (root / ".cursor" / "rules" / "oldhand.mdc",
                "---\n"
                "description: Consult local Oldhand records for prior engineering constraints and decisions.\n"
                "---\n\n", False)
    # The research established no isolated project target for either of these
    # harnesses.  Never invent one or create a shared instruction file.
    return root / "AGENTS.md", "", True


def _setup_block() -> str:
    return f"{SETUP_START}\n{SETUP_GUIDANCE}{SETUP_END}\n"


def _safe_setup_path(root: Path, path: Path) -> bool:
    """Reject a setup target that reaches outside --root through a symlink."""
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        print(f"Refusing setup path outside repository root: {path}", file=sys.stderr)
        return False


def _owned_setup_range(content: str) -> tuple[int, int] | None:
    starts = [match.start() for match in re.finditer(re.escape(SETUP_START), content)]
    ends = [match.start() for match in re.finditer(re.escape(SETUP_END), content)]
    if not starts and not ends:
        return None
    if len(starts) != 1 or len(ends) != 1 or ends[0] < starts[0]:
        raise ValueError("malformed Oldhand setup ownership markers")
    end = ends[0] + len(SETUP_END)
    if end < len(content) and content[end:end + 1] == "\n":
        end += 1
    return starts[0], end


def _setup_diff(path: Path, before: str, after: str) -> None:
    for line in difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=f"a/{path.as_posix()}", tofile=f"b/{path.as_posix()}",
    ):
        print(line, end="")


def setup_harness(root: Path, harness: str, apply: bool = False,
                  undo: bool = False) -> int:
    """Preview or apply a minimal, owned harness instruction change.

    This command intentionally has no side effects unless --apply is given.
    It is not an integration installer: it never creates hooks, MCP settings,
    credentials, user-level files, or a root AGENTS.md for shared harnesses.
    """
    root = root.resolve()
    target, prefix, requires_existing = _setup_target(root, harness)
    if not _safe_setup_path(root, target):
        return 1
    exists = target.exists()
    if exists and not target.is_file():
        print(f"Refusing setup target that is not a regular file: {target}", file=sys.stderr)
        return 1
    if requires_existing and not exists:
        print(f"{harness} uses a repository AGENTS.md. None exists at {root}; "
              "Oldhand will not create one. Add the Oldhand guidance manually or create "
              "AGENTS.md for your own project instructions first.", file=sys.stderr)
        return 1
    try:
        before = target.read_text(encoding="utf-8") if exists else ""
    except (OSError, UnicodeError) as error:
        print(f"Could not read setup target {target}: {error}", file=sys.stderr)
        return 1
    try:
        owned = _owned_setup_range(before)
    except ValueError as error:
        print(f"Refusing setup change in {target}: {error}.", file=sys.stderr)
        return 1

    rendered = prefix + _setup_block()
    if undo:
        if owned is None:
            print(f"No Oldhand-owned setup content found in {target}.")
            return 0
        after = before[:owned[0]] + before[owned[1]:]
        # A dedicated file that remains exactly Oldhand's generated shell is also
        # wholly owned, so it can be removed. Never delete a file that includes
        # any user content.
        delete_target = (not requires_existing and before == rendered)
        if delete_target:
            after = ""
    else:
        if owned is not None:
            after = before[:owned[0]] + _setup_block() + before[owned[1]:]
        elif exists and not requires_existing and before.strip():
            print(f"Refusing to overwrite existing dedicated setup file: {target}. "
                  "Add Oldhand's marked block manually or use --undo only for content "
                  "owned by Oldhand.", file=sys.stderr)
            return 1
        elif exists:
            after = before + ("" if not before or before.endswith("\n") else "\n") + _setup_block()
        else:
            after = rendered
        delete_target = False

    if after == before:
        print(f"Oldhand setup for {harness} is already up to date: {target}")
        return 0
    _setup_diff(target.relative_to(root), before, after)
    if not apply:
        print("Dry run only. Re-run with --apply to write this change.")
        return 0
    try:
        if delete_target:
            target.unlink()
            print(f"Removed Oldhand-owned setup file: {target}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not _safe_setup_path(root, target):
                return 1
            _atomic_write(target, after.encode("utf-8"))
            print(f"Applied Oldhand setup for {harness}: {target}")
    except OSError as error:
        print(f"Could not write setup target {target}: {error}", file=sys.stderr)
        return 1
    return 0


def _records_for_mutation(root: Path) -> dict[str, dict[str, Any]] | None:
    records, errors, _ = validate_records(root)
    if errors:
        print("Refusing to modify an invalid archive. Run `oldhand validate`:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return None
    return {str(record["meta"]["id"]): record for record in records}


def _render_record(record: dict[str, Any], meta: dict[str, Any]) -> str:
    frontmatter = yaml.safe_dump(
        meta, sort_keys=False, allow_unicode=True, default_flow_style=False
    ).rstrip()
    return f"---\n{frontmatter}\n---\n\n{record['body'].rstrip()}\n"




def _publish_record_updates(root: Path, records: dict[str, dict[str, Any]],
                            updates: dict[str, dict[str, Any]]) -> bool:
    originals = {rid: records[rid]["path"].read_bytes() for rid in updates}
    try:
        for rid, meta in updates.items():
            rendered = _render_record(records[rid], meta).encode("utf-8")
            _atomic_write(records[rid]["path"], rendered)
        _, errors, _ = validate_records(root)
        if errors:
            raise ValueError("; ".join(errors))
    except BaseException as error:
        for rid, data in originals.items():
            _atomic_write(records[rid]["path"], data)
        print(f"Record update failed and was rolled back: {error}", file=sys.stderr)
        return False
    rebuild(root, strict=True, quiet=True)
    return True


def rename_record_id(root: Path, old_id: str, new_id: str) -> int:
    """Rename an id and rewrite every incoming relation atomically."""
    if not RECORD_ID_RE.fullmatch(new_id):
        print("Invalid id: use 1-128 letters, digits, dots, underscores, or hyphens; start with a letter or digit.",
              file=sys.stderr)
        return 2
    records = _records_for_mutation(root)
    if records is None:
        return 1
    if old_id not in records:
        print(f"Unknown record id: {old_id}", file=sys.stderr)
        return 1
    if old_id == new_id:
        print(f"Record already has id {old_id}")
        return 0
    if new_id in records:
        print(f"Record id already exists: {new_id}", file=sys.stderr)
        return 1

    now = datetime.now().astimezone().replace(microsecond=0).isoformat()
    updates: dict[str, dict[str, Any]] = {}
    renamed = dict(records[old_id]["meta"])
    renamed["id"] = new_id
    renamed["updated_at"] = now
    updates[old_id] = renamed
    for rid, record in records.items():
        if rid == old_id:
            continue
        changed = False
        relations = {key: list(values) for key, values in record["relations"].items()}
        for relation_type, targets in relations.items():
            if old_id in targets:
                relations[relation_type] = sorted(set(
                    new_id if target == old_id else target for target in targets
                ))
                changed = True
        if changed:
            meta = dict(record["meta"])
            meta["relations"] = relations
            meta["updated_at"] = now
            updates[rid] = meta
    if not _publish_record_updates(root, records, updates):
        return 1
    print(f"Renamed {old_id} -> {new_id}; updated {len(updates) - 1} backlink record(s)")
    return 0


def curate_topic(root: Path, record_id: str, add: str | None = None,
                 remove: str | None = None) -> int:
    records = _records_for_mutation(root)
    if records is None:
        return 1
    if record_id not in records:
        print(f"Unknown record id: {record_id}", file=sys.stderr)
        return 1
    topic = (add or remove or "").strip()
    if not topic:
        print("Topic cannot be empty.", file=sys.stderr)
        return 2
    meta = dict(records[record_id]["meta"])
    raw_topics = meta.get("topics", [])
    topics = [str(raw_topics)] if isinstance(raw_topics, str) else list(raw_topics)
    key = topic.casefold().replace(" ", "-")
    keys = [str(item).casefold().replace(" ", "-") for item in topics]
    if add is not None:
        if key in keys:
            print(f"Record {record_id} already has topic {topic}")
            return 0
        topics.append(topic)
        action = "Added"
    else:
        if key not in keys:
            print(f"Record {record_id} does not have topic {topic}", file=sys.stderr)
            return 1
        if len(topics) == 1:
            print("A record must retain at least one topic.", file=sys.stderr)
            return 1
        topics.pop(keys.index(key))
        action = "Removed"
    meta["topics"] = topics
    meta["updated_at"] = datetime.now().astimezone().replace(microsecond=0).isoformat()
    if not _publish_record_updates(root, records, {record_id: meta}):
        return 1
    print(f"{action} topic {topic} {'to' if add is not None else 'from'} {record_id}")
    return 0


def classify_record(root: Path, record_id: str, **changes: str | None) -> int:
    selected = {key: value for key, value in changes.items() if value is not None}
    if not selected:
        print("Provide at least one classification option.", file=sys.stderr)
        return 2
    records = _records_for_mutation(root)
    if records is None:
        return 1
    if record_id not in records:
        print(f"Unknown record id: {record_id}", file=sys.stderr)
        return 1
    meta = dict(records[record_id]["meta"])
    meta.update(selected)
    meta["updated_at"] = datetime.now().astimezone().replace(microsecond=0).isoformat()
    if not _publish_record_updates(root, records, {record_id: meta}):
        return 1
    rendered = ", ".join(f"{key}={value}" for key, value in selected.items())
    print(f"Classified {record_id}: {rendered}")
    return 0


def compact_records(root: Path, target_id: str, source_ids: list[str],
                    dry_run: bool = False, json_output: bool = False) -> int:
    """Retire several records into an already-prepared canonical target."""
    records = _records_for_mutation(root)
    if records is None:
        return 1
    sources = list(dict.fromkeys(source_ids))
    if target_id not in records:
        print(f"Unknown target record id: {target_id}", file=sys.stderr)
        return 1
    if str(records[target_id]["meta"].get("status")) in RETIRED_STATUSES:
        print(f"Target record '{target_id}' is retired.", file=sys.stderr)
        return 1
    for source_id in sources:
        if source_id == target_id:
            print("Target cannot also be a source.", file=sys.stderr)
            return 1
        if source_id not in records:
            print(f"Unknown source record id: {source_id}", file=sys.stderr)
            return 1
        if str(records[source_id]["meta"].get("status")) in RETIRED_STATUSES:
            print(f"Source record '{source_id}' is already retired.", file=sys.stderr)
            return 1

    plan = {
        "target": target_id, "sources": sources, "dry_run": dry_run,
        "changes": {
            target_id: {"add_relation": {"supersedes": sources}},
            **{source_id: {"status": "superseded"} for source_id in sources},
        },
    }
    if dry_run:
        if json_output:
            print(json.dumps(plan, ensure_ascii=False, indent=2))
        else:
            print(f"Would compact {', '.join(sources)} into {target_id}")
            print("No record bodies would be changed.")
        return 0

    now = datetime.now().astimezone().replace(microsecond=0).isoformat()
    updates: dict[str, dict[str, Any]] = {}
    target_meta = dict(records[target_id]["meta"])
    relations = {key: list(values) for key, values in records[target_id]["relations"].items()}
    relations["supersedes"] = sorted(set(relations.get("supersedes", [])) | set(sources))
    target_meta["relations"] = relations
    target_meta["updated_at"] = now
    updates[target_id] = target_meta
    for source_id in sources:
        meta = dict(records[source_id]["meta"])
        meta["status"] = "superseded"
        meta["updated_at"] = now
        updates[source_id] = meta
    if not _publish_record_updates(root, records, updates):
        return 1
    plan["dry_run"] = False
    if json_output:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        print(f"Compacted {', '.join(sources)} into {target_id}")
        print("Canonical bodies were preserved; sources are now superseded.")
    return 0


def relate(root: Path, source_id: str, relation_type: str, target_id: str) -> int:
    records = _records_for_mutation(root)
    if records is None:
        return 1
    if source_id not in records:
        print(f"Unknown source record id: {source_id}", file=sys.stderr)
        return 1
    if target_id not in records:
        print(f"Unknown target record id: {target_id}", file=sys.stderr)
        return 1
    if source_id == target_id:
        print("A record cannot relate to itself.", file=sys.stderr)
        return 1
    if relation_type == "supersedes" and str(
        records[target_id]["meta"].get("status")
    ) not in RETIRED_STATUSES:
        print(
            f"Cannot supersede active record '{target_id}'; use `oldhand supersede`.",
            file=sys.stderr,
        )
        return 1

    meta = dict(records[source_id]["meta"])
    relations = {key: list(values) for key, values in records[source_id]["relations"].items()}
    targets = relations.setdefault(relation_type, [])
    if target_id in targets:
        print(f"Relation already exists: {source_id} {relation_type} {target_id}")
        return 0
    targets.append(target_id)
    targets.sort()
    meta["relations"] = relations
    meta["updated_at"] = datetime.now().astimezone().replace(microsecond=0).isoformat()
    if not _publish_record_updates(root, records, {source_id: meta}):
        return 1
    print(f"Related {source_id} {relation_type} {target_id}")
    return 0


def unrelate(root: Path, source_id: str, relation_type: str, target_id: str) -> int:
    records = _records_for_mutation(root)
    if records is None:
        return 1
    if source_id not in records:
        print(f"Unknown source record id: {source_id}", file=sys.stderr)
        return 1
    if target_id not in records:
        print(f"Unknown target record id: {target_id}", file=sys.stderr)
        return 1
    relations = {key: list(values) for key, values in records[source_id]["relations"].items()}
    targets = relations.get(relation_type, [])
    if target_id not in targets:
        print(
            f"Relation does not exist: {source_id} {relation_type} {target_id}",
            file=sys.stderr,
        )
        return 1
    targets.remove(target_id)
    if targets:
        relations[relation_type] = targets
    else:
        relations.pop(relation_type, None)
    meta = dict(records[source_id]["meta"])
    meta["relations"] = relations
    meta["updated_at"] = datetime.now().astimezone().replace(microsecond=0).isoformat()
    if not _publish_record_updates(root, records, {source_id: meta}):
        return 1
    print(f"Removed relation {source_id} {relation_type} {target_id}")
    return 0


def supersede_record(root: Path, old_id: str, new_id: str) -> int:
    records = _records_for_mutation(root)
    if records is None:
        return 1
    if old_id not in records:
        print(f"Unknown old record id: {old_id}", file=sys.stderr)
        return 1
    if new_id not in records:
        print(f"Unknown replacement record id: {new_id}", file=sys.stderr)
        return 1
    if old_id == new_id:
        print("A record cannot supersede itself.", file=sys.stderr)
        return 1
    if str(records[new_id]["meta"].get("status")) in RETIRED_STATUSES:
        print(f"Replacement record '{new_id}' is retired.", file=sys.stderr)
        return 1

    new_relations = {
        key: list(values) for key, values in records[new_id]["relations"].items()
    }
    superseded = new_relations.setdefault("supersedes", [])
    already_complete = (
        str(records[old_id]["meta"].get("status")) == "superseded"
        and old_id in superseded
    )
    if already_complete:
        print(f"Supersession already exists: {new_id} supersedes {old_id}")
        return 0
    if old_id not in superseded:
        superseded.append(old_id)
        superseded.sort()

    now = datetime.now().astimezone().replace(microsecond=0).isoformat()
    old_meta = dict(records[old_id]["meta"])
    old_meta["status"] = "superseded"
    old_meta["updated_at"] = now
    new_meta = dict(records[new_id]["meta"])
    new_meta["relations"] = new_relations
    new_meta["updated_at"] = now
    if not _publish_record_updates(
        root, records, {old_id: old_meta, new_id: new_meta}
    ):
        return 1
    print(f"Superseded {old_id} with {new_id}")
    return 0


def set_record_status(root: Path, record_id: str, status: str) -> int:
    if status not in DIRECT_STATUSES:
        print(
            "Status 'superseded' requires `oldhand supersede OLD --by NEW`.",
            file=sys.stderr,
        )
        return 1
    records = _records_for_mutation(root)
    if records is None:
        return 1
    if record_id not in records:
        print(f"Unknown record id: {record_id}", file=sys.stderr)
        return 1
    current = str(records[record_id]["meta"].get("status"))
    if current == status:
        print(f"Record {record_id} already has status {status}")
        return 0
    meta = dict(records[record_id]["meta"])
    meta["status"] = status
    meta["updated_at"] = datetime.now().astimezone().replace(microsecond=0).isoformat()
    if not _publish_record_updates(root, records, {record_id: meta}):
        return 1
    print(f"Changed {record_id}: {current} -> {status}")
    return 0


def slugify(text: str, max_len: int = 48) -> str:
    s = SLUG_STRIP_RE.sub("-", text.lower()).strip("-")
    if len(s) > max_len:
        s = s[:max_len].rstrip("-")
    return s or "record"


def existing_ids(root: Path) -> set[str]:
    ids: set[str] = set()
    for collection_root in discover_collections(root):
        for p in record_files(collection_root):
            try:
                m = FRONTMATTER_RE.match(p.read_text(encoding="utf-8"))
                if not m:
                    continue
                meta = yaml.safe_load(m.group(1)) or {}
                if isinstance(meta, dict) and meta.get("id"):
                    ids.add(str(meta["id"]))
            except Exception:
                continue
    return ids


def resolve_target_collection(root: Path, name: str | None) -> Path:
    collections = discover_collections(root)
    if not name:
        if root in collections or not collections:
            return root
        return collections[0]
    for c in collections:
        if collection_name(root, c) == name:
            return c
    known = ", ".join(collection_name(root, c) for c in collections) or "none"
    print(f"Unknown collection '{name}'. Known collections: {known}", file=sys.stderr)
    raise SystemExit(2)


def new_record(root: Path, args: argparse.Namespace) -> int:
    """Write a well-formed record skeleton.

    Bookkeeping (id, timestamps, file location, section headings) is generated
    here so the model only has to supply knowledge. Hand-written frontmatter was
    the main source of records that failed validation.
    """
    target_root = resolve_target_collection(root, args.collection)
    topics = [t.strip() for t in (args.topics or "").split(",") if t.strip()]

    taken = existing_ids(root)
    explicit_id = getattr(args, "id", None)
    if explicit_id:
        if not RECORD_ID_RE.fullmatch(explicit_id):
            print(
                "Invalid record id. Use 1-128 letters, numbers, dots, underscores, or hyphens; "
                "start with a letter or number.",
                file=sys.stderr,
            )
            return 2
        if explicit_id in taken:
            print(f"Record id already exists: {explicit_id}", file=sys.stderr)
            return 1
        rid = explicit_id
    else:
        base = "lore_" + slugify(args.title).replace("-", "_")
        rid = base
        while rid in taken:
            suffix = hashlib.sha1(f"{rid}:{datetime.now().isoformat()}".encode()).hexdigest()[:4]
            rid = f"{base}_{suffix}"

    now = datetime.now().astimezone().replace(microsecond=0).isoformat()
    directory = target_root / "memory" / TYPE_DIRS[args.type]
    path = directory / f"{slugify(args.title)}.md"
    if path.exists():
        print(f"Refusing to overwrite existing file: {display_path(root, path)}", file=sys.stderr)
        return 1

    topic_lines = yaml.safe_dump(
        topics or ["untriaged"], default_flow_style=False,
        allow_unicode=True).strip()
    summary = args.summary or "One or two sentences a future agent can rank on."
    knowledge = args.knowledge or (
        "What a future engineer or agent needs to know. Leave out anything that code,\n"
        "Git, tests, or current documentation already preserve cheaply."
    )
    verification = args.verification or "How this was established, and what was not verified."
    references = getattr(args, "references", None) or "-"

    content = f"""---
schema_version: 1
id: {rid}
type: {args.type}
status: {args.status}
importance: {args.importance}
scope: {args.scope}
risk: {args.risk}
durability: {args.durability}
evidence: {args.evidence}
topics:
{topic_lines}
created_at: {now}
updated_at: {now}
expires_at: null
relations: {{}}
---

# {args.title}

## Summary

{summary}

## Knowledge

{knowledge}

## Verification

{verification}

## References

{references}
"""
    if getattr(args, "dry_run", False):
        if getattr(args, "json_output", False):
            print(json.dumps({
                "created": False, "dry_run": True, "id": rid,
                "path": display_path(root, path),
                "collection": collection_name(root, target_root),
                "content": content,
            }, ensure_ascii=False, indent=2))
        else:
            print(content, end="")
        return 0

    directory.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    if getattr(args, "json_output", False):
        print(json.dumps({
            "created": True, "dry_run": False, "id": rid,
            "path": display_path(root, path),
            "collection": collection_name(root, target_root),
        }, ensure_ascii=False, indent=2))
    else:
        print(f"Created {display_path(root, path)}")
        print(f"id: {rid}")
        print("Fill in Summary, Knowledge, Verification and References,")
        print("then run: oldhand rebuild")
    return 0


def distill_run(root: Path, args: argparse.Namespace) -> int:
    valid, errors = experience.validate_runs(root, args.run_id)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    run = valid[0]
    if run.get("status") != "completed":
        print("Distillation requires a completed discovery run.", file=sys.stderr)
        return 1
    node = next((item for item in run["nodes"] if item["id"] == args.node_id), None)
    if node is None:
        print(f"Unknown attempt: {args.node_id}", file=sys.stderr)
        return 1
    evaluation = node.get("evaluation")
    if not evaluation:
        print(f"Attempt is not evaluated: {args.node_id}", file=sys.stderr)
        return 1
    state = "correct" if evaluation["correct"] else "incorrect"
    summary = args.summary or (
        f"Discovery attempt '{node['proposal']}' evaluated {state} with score "
        f"{evaluation['score']:g} under {run['evaluator']}."
    )
    knowledge = (
        f"Proposal: {node['proposal']}\n\n"
        f"Recorded outcome: {evaluation['outcome']}. Score: {evaluation['score']:g}. "
        f"Recorded cost: {evaluation['cost']}."
    )
    if node.get("artifact_ref"):
        knowledge += f"\n\nArtifact: {node['artifact_ref']}"
    verification = (
        f"Evaluator: {run['evaluator']}. Correctness: {state}. "
        f"Duration: {evaluation['duration_ms']} ms."
    )
    if evaluation.get("diagnostics_ref"):
        verification += f" Diagnostics: {evaluation['diagnostics_ref']}."
    record_args = argparse.Namespace(
        id=args.id, title=args.title, type=args.entry_type,
        importance=args.importance, topics=args.topics,
        status="current", scope=args.scope, risk=args.risk,
        durability=args.durability,
        evidence="verified" if evaluation["correct"] else "observed",
        summary=summary, knowledge=knowledge, verification=verification,
        references=f"- experience/runs/{run['id']}.json (attempt `{node['id']}`)",
        collection=args.collection, json_output=args.json_output,
        dry_run=args.dry_run,
    )
    return new_record(root, record_args)
