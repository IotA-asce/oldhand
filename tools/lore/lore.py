#!/usr/bin/env python3
"""
Lore: durable engineering memory for coding agents.

Canonical knowledge lives in Markdown under memory/.
SQLite is derived and can be rebuilt at any time.

Design contract:
  - validate  is the strict gate: any problem is an error and exits 1.
  - rebuild   is fail-open: it indexes every valid record, reports the ones it
              skipped, and still leaves a usable index behind.
  - search    and show never die because one record is malformed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("Missing dependency: PyYAML. Install with: python -m pip install PyYAML", file=sys.stderr)
    raise SystemExit(2)

# Bumped when indexing or scoring changes in a way that moves retrieval, so
# metrics from different archives can be compared like with like.
LORE_VERSION = "0.4.4"

ENTRY_TYPES = {
    "topic_summary", "decision", "constraint", "fix",
    "investigation", "migration", "incident", "lesson", "reference",
    "feature",
}
# Keep in step with the entry_type CHECK in schema.sql and with TYPE_DIRS
# below. Asserted by `lore selftest`, because the two lists drifting apart
# rejects every record of the new type while the schema happily accepts it.
STATUSES = {"current", "resolved", "superseded", "deprecated", "historical"}
IMPORTANCE = {"critical", "high", "normal", "low"}
SCOPES = {"workspace", "repository", "subsystem", "feature", "local"}
RISKS = {"critical", "high", "medium", "low", "none"}
DURABILITY = {"invariant", "long_lived", "situational", "temporary"}
EVIDENCE = {"verified", "documented", "observed", "inferred"}
RELATION_TYPES = {"supersedes", "depends_on", "related_to", "caused_by", "contradicts"}

# A record is retired once it carries one of these statuses.
RETIRED_STATUSES = {"superseded", "deprecated"}
DIRECT_STATUSES = STATUSES - {"superseded"}

# Directory each entry type is filed under by `lore new`.
TYPE_DIRS = {
    "topic_summary": "topics",
    "decision": "decisions",
    "constraint": "constraints",
    "fix": "fixes",
    "investigation": "investigations",
    "migration": "migrations",
    "incident": "incidents",
    "lesson": "lessons",
    "reference": "reference",
    "feature": "features",
}

# Retrieval scoring.
#
# Textual relevance contributes 0..TEXT_WEIGHT and must stay the dominant term.
# Metadata breaks ties between comparable matches; it does not decide the
# ranking. The sum of every positive metadata boost is deliberately held below
# TEXT_WEIGHT, so no combination of labels can promote a record over one that
# matches the query substantially better.
#
# This is not a taste preference. An earlier version let importance + risk +
# durability reach 60, exactly the whole text range, which made a single
# `critical` label worth as much as perfect textual relevance. Measured on a
# 117-record archive: recall@5 fell from 92% to 33% once a quarter of the
# records carried that label, and nothing in the design resists label
# inflation. With these weights the same corpus and queries hold 83% to 75%
# across the same range. Raise any of these numbers and re-run that curve
# before believing it is still safe.
#
# Evidence carries weight because `verified` versus `inferred` is the one
# metadata distinction that is checkable at write time rather than guessed.
#
# The importance ladder is deliberately shallow. `lore doctor` measures how
# many records are returned first for a query made of their own title; with
# critical at 12, seven records were losing to one of only FOUR critical
# records, at 3.4% of the archive. Dropping it to 4 raised findability from
# 92% to 95% and changed eval recall and MRR by nothing at all, so the extra
# weight was buying no relevance and costing reach. Importance survives as a
# tiebreak; the unbounded safety pass, not the boost, is what guarantees a
# critical record is always considered.
TEXT_WEIGHT = 60.0
TOPIC_BOOST_PER_HIT = 6
TOPIC_BOOST_CAP = 12
SCOPE_MATCH_BOOST = 5
IMPORTANCE_BOOST = {"critical": 4, "high": 3, "normal": 2, "low": 0}
RISK_BOOST = {"critical": 6, "high": 4, "medium": 2, "low": 1, "none": 0}
DURABILITY_BOOST = {"invariant": 6, "long_lived": 3, "situational": 1, "temporary": 0}
STATUS_BOOST = {"current": 6, "resolved": 3, "historical": 1, "superseded": -30, "deprecated": -30}
EVIDENCE_BOOST = {"verified": 5, "documented": 3, "observed": 1, "inferred": 0}

# Invariant guarded by `lore selftest`: metadata can never outvote text.
MAX_METADATA_BOOST = (
    max(IMPORTANCE_BOOST.values()) + max(RISK_BOOST.values())
    + max(DURABILITY_BOOST.values()) + max(STATUS_BOOST.values())
    + max(EVIDENCE_BOOST.values()) + TOPIC_BOOST_CAP + SCOPE_MATCH_BOOST
)

# FTS column weights, in entry_fts order: entry_id, title, summary, body,
# topics. Equal weighting lets a 5,000-word record outrank a precise one just
# by containing more words. Measured on a 293-record archive: these values
# moved MRR from 0.67 to 0.71 and recall@1 from 55% to 64%.
#
# Provisional. They were swept against an eval set whose queries all target
# one of four collections, so they are tuned for that slice. Re-sweep once the
# eval set covers the whole archive.

# Points deducted when a hit comes from a section passage rather than the
# whole record. Aboutness beats mention, but only just.
#
# Swept against eval, findability and secondary-finding reachability together,
# because optimising eval alone fits 46 hand-written queries, and a penalty
# large enough to help eval can undo the reason sections are indexed at all.
# 3.0 was best on all three at once (r@1 78->80%, findability 98->99%, reach
# unchanged at 82%); 14.0 was worse than no penalty on every measure.
#
# That sweep ran while search collapsed candidate rows by bm25 before scoring,
# so this penalty could land on a record that also matched as a whole, and a
# large value could drop such a record out of the results entirely. 0.4.3
# collapses rows after scoring instead, so a record now scores at least as well
# as its whole-record row whatever this value is: raising it can no longer
# evict anything, only decline to promote a section-only match. Measured on a
# 216-record corpus, recall@3 and recall@5 held at 100% across 0.0 to 14.0
# after the change, where before it they fell to 31% and 25% at 10.0 and 14.0.
#
# 3.0 is therefore retained rather than re-derived. It was calibrated partly
# against collateral damage that no longer exists, so there is headroom above
# it, but nothing available here can say how much. Settling that needs an
# archive whose records genuinely mention each other's subjects in passing;
# a synthetic corpus cannot, because whichever text is written closer to the
# query wins, and the same hand writes both. Re-sweep when a real archive with
# section rows is available.
SECTION_PENALTY = 3.0

# Token appended to a section row's topics column to mark it. Never a real
# topic; stripped before topic matching so it cannot earn a topic boost.
SECTION_MARKER = "zzsectionrow"

# Searches needed before "never retrieved" means anything but "not yet asked".
EVIDENCE_THRESHOLD = 50

# Share of the archive above which `critical` has stopped discriminating.
CRITICAL_SHARE_LIMIT = 0.10

# Candidate pool for the relevance pass. The safety pass is unbounded, so a
# critical record can never be cut by this limit.
RELEVANCE_POOL = 500

# Directories never searched for collections.
PRUNE_DIRS = {
    ".git", ".hg", ".svn", ".lore", "node_modules", "__pycache__",
    ".venv", "venv", "env", "dist", "build", "bin", "obj", "target",
    "packages", "vendor",
}

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
HEADING_RE = re.compile(r"^#\s+(.+?)\s*$", re.M)
SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)
QUERY_WORD_RE = re.compile(r"[\w.:/+-]+")
SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")
RECORD_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


# --------------------------------------------------------------------------
# Roots and collections
# --------------------------------------------------------------------------

def workspace_root(explicit: str | None) -> Path:
    """Resolve the workspace root.

    Precedence: --root, then LORE_ROOT, then the *topmost* marker-bearing
    ancestor of the current directory. Taking the topmost rather than the
    nearest marker means running from inside a repository still searches the
    whole workspace; use --root to deliberately narrow the scope.
    """
    if explicit:
        return Path(explicit).resolve()
    env = os.environ.get("LORE_ROOT")
    if env:
        return Path(env).resolve()

    cur = Path.cwd().resolve()
    try:
        home = Path.home().resolve()
    except Exception:
        home = None

    best: Path | None = None
    for candidate in [cur, *cur.parents]:
        if (candidate / "AGENTS.md").exists() or (candidate / "memory").is_dir():
            best = candidate
        if home is not None and candidate == home:
            break
    return best or cur


def discover_collections(root: Path, max_depth: int = 4) -> list[Path]:
    """Find every directory that owns a `memory/` archive, root included.

    A workspace holds one archive per repository. Sub-collections are not
    descended into, so a repository's own subdirectories never become separate
    collections.
    """
    found: list[Path] = []
    root_memory = root / "memory"
    # The CLI's own directory is not an archive, even if someone relocates it
    # next to one. Without this
    # guard the starter indexes its own source directory as a collection.
    tool_dir = Path(__file__).resolve().parent

    def is_archive(candidate: Path) -> bool:
        mem = candidate / "memory"
        if not mem.is_dir():
            return False
        try:
            return mem.resolve() != tool_dir
        except OSError:
            return True

    if is_archive(root):
        found.append(root)

    def walk(directory: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            children = sorted(p for p in directory.iterdir() if p.is_dir())
        except (PermissionError, OSError):
            return
        for child in children:
            if child.name in PRUNE_DIRS or child.name.startswith("."):
                continue
            if child == root_memory:
                continue
            if is_archive(child):
                found.append(child)
                continue
            walk(child, depth + 1)

    walk(root, 1)
    return found


def collection_name(root: Path, collection_root: Path) -> str:
    if collection_root == root:
        return root.name or str(root)
    try:
        return collection_root.relative_to(root).as_posix()
    except ValueError:
        return str(collection_root)


def collection_id(root: Path, collection_root: Path) -> str:
    rel = collection_name(root, collection_root)
    return "col:" + hashlib.sha1(rel.encode("utf-8")).hexdigest()[:12]


def db_path(root: Path) -> Path:
    return root / ".lore" / "lore.db"


def schema_path() -> Path:
    """Resolve the schema next to this script, not next to the detected root.

    Anchoring it to the root made the CLI unusable from any directory that did
    not happen to carry its own copy of the tool.
    """
    p = Path(__file__).resolve().parent / "schema.sql"
    if not p.exists():
        raise FileNotFoundError(f"Missing schema: {p}")
    return p


def display_path(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


# --------------------------------------------------------------------------
# Record parsing
# --------------------------------------------------------------------------

def parse_sections(body: str) -> dict[str, str]:
    matches = list(SECTION_RE.finditer(body))
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections[m.group(1).strip().lower()] = body[start:end].strip()
    return sections


def normalize_relations(value: Any) -> dict[str, list[str]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("relations must be a mapping")
    out: dict[str, list[str]] = {}
    for k, v in value.items():
        if k not in RELATION_TYPES:
            raise ValueError(f"invalid relation type '{k}'")
        targets = [v] if isinstance(v, str) else v
        if not isinstance(targets, list) or any(
            not isinstance(target, str) or not target.strip() for target in targets
        ):
            raise ValueError(f"relation '{k}' must contain nonempty string targets")
        out[k] = targets
    return out


def parse_record(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError("missing YAML frontmatter")
    meta = yaml.safe_load(m.group(1)) or {}
    if not isinstance(meta, dict):
        raise ValueError("frontmatter must be a mapping")

    body = text[m.end():].strip()
    hm = HEADING_RE.search(body)
    title = hm.group(1).strip() if hm else str(meta.get("title") or path.stem)
    sections = parse_sections(body)

    topics = meta.get("topics") or []
    if isinstance(topics, str):
        topics = [topics]
    topics = [str(x).strip() for x in topics if str(x).strip()]

    return {
        "meta": meta,
        "title": title,
        "summary": sections.get("summary", "").strip(),
        "sections": sections,
        "body": body,
        "topics": topics,
        "relations": normalize_relations(meta.get("relations")),
        "text": text,
    }


def record_files(collection_root: Path) -> list[Path]:
    mem = collection_root / "memory"
    if not mem.is_dir():
        return []
    files = []
    for p in mem.rglob("*.md"):
        if p.name in {"README.md", "SCHEMA.md", "MEMORY_INDEX.md"}:
            continue
        # examples document the format but are not live memory
        if "examples" in p.parts:
            continue
        files.append(p)
    return sorted(files)


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# Index build
# --------------------------------------------------------------------------

def connect(root: Path) -> sqlite3.Connection:
    db = db_path(root)
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    return con


def token_estimate(text: str) -> int:
    # Deliberately deterministic, dependency-free approximation.
    return max(1, round(len(text) / 4))


# Headings that label a record's structure rather than name a finding. A
# section called "Context" is not a subject anyone searches for.
_STRUCTURAL_HEADING = re.compile(
    r"^(context|changes|links|summary|from the summary|risks|testing|"
    r"follow.?up|rollback|verification|references|knowledge|what changed"
    r"( and why it mattered)?|background|overview)\b",
    re.I)

# A passage shorter than this is a label, not a finding, and indexing it adds
# noise with no reach.
_MIN_SECTION_CHARS = 200


def split_sections(body: str) -> list[tuple[str, str]]:
    """Split a record body into (heading, passage) pairs worth indexing.

    Only sections that name something. Structural headings are skipped, as are
    passages too short to carry a finding, so a small record produces no extra
    rows at all and the index stays close to one row per record.
    """
    parts = re.split(r"^(#{2,4})\s+(.+?)\s*$", body, flags=re.M)
    if len(parts) < 4:
        return []
    out: list[tuple[str, str]] = []
    # re.split with two groups yields: [pre, hashes, heading, text, hashes, ...]
    for i in range(1, len(parts) - 2, 3):
        heading = parts[i + 1].strip()
        passage = parts[i + 2].strip()
        if _STRUCTURAL_HEADING.match(heading):
            continue
        if len(passage) < _MIN_SECTION_CHARS:
            continue
        out.append((heading, passage))
    return out


# Identifier shapes worth expanding: camelCase, PascalCase, snake_case and
# dotted paths. A word with no internal boundary is left alone, so ordinary
# prose is never split into terms nobody wrote.
_IDENT = re.compile(r"\b(?=\w*[a-z])(?=\w*[A-Z_.])[A-Za-z][A-Za-z0-9_.]{2,}\b")
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z0-9]+|[A-Z]+")


def expand_identifiers(text: str) -> str:
    """Component words of every identifier in `text`, space separated.

    Returns only the added terms, never the original, so callers decide where
    to append them. An empty string when there is nothing identifier-shaped,
    which is the common case for prose.
    """
    if not text:
        return ""
    out: list[str] = []
    seen: set[str] = set()
    for match in _IDENT.finditer(text):
        token = match.group(0)
        parts = [w for chunk in token.replace(".", "_").split("_") if chunk
                 for w in _CAMEL.findall(chunk)]
        parts = [w.lower() for w in parts if len(w) > 1]
        # One part means the split found nothing the tokenizer had not already.
        if len(parts) < 2:
            continue
        for w in parts:
            if w not in seen:
                seen.add(w)
                out.append(w)
    return " ".join(out)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def archive_fingerprint(root: Path) -> str:
    """Cheap staleness signal: which files exist and what each contains."""
    digest = hashlib.sha256()
    count = 0
    for collection_root in discover_collections(root):
        for p in record_files(collection_root):
            count += 1
            digest.update(str(p.relative_to(root)).encode("utf-8"))
            digest.update(b"\0")
            try:
                digest.update(p.read_bytes())
            except OSError:
                pass
            digest.update(b"\0")
    return f"{count}:{digest.hexdigest()[:16]}"


def rebuild(root: Path, strict: bool = False, quiet: bool = False) -> int:
    """Build the index from every valid record.

    Fail-open by design: one malformed record is skipped and reported, it does
    not take the rest of the archive offline. Use `validate` (or --strict) when
    a hard gate is wanted.
    """
    records, errors, warnings = validate_records(root)

    db = db_path(root)
    db.parent.mkdir(parents=True, exist_ok=True)
    fd, staging_name = tempfile.mkstemp(prefix=db.name + ".building.", dir=db.parent)
    os.close(fd)
    staging = Path(staging_name)

    collections = discover_collections(root)
    con = None
    try:
        con = sqlite3.connect(staging)
        con.row_factory = sqlite3.Row
        con.executescript(schema_path().read_text(encoding="utf-8"))

        multi = len(collections) > 1
        col_ids: dict[Path, str] = {}
        for collection_root in collections:
            cid = collection_id(root, collection_root)
            col_ids[collection_root] = cid
            kind = "workspace" if (multi and collection_root == root) else "repository"
            con.execute(
                "INSERT INTO collections(id, kind, name, root_path) VALUES (?,?,?,?)",
                (cid, kind, collection_name(root, collection_root), str(collection_root)),
            )

        topic_ids: dict[tuple[str, str], int] = {}
        for r in records:
            meta = r["meta"]
            rid = str(meta["id"])
            cid = col_ids[r["collection_root"]]
            rel_path = r["path"].relative_to(r["collection_root"]).as_posix()
            expires = meta.get("expires_at")
            if expires is not None:
                expires = str(expires)

            con.execute(
                """INSERT INTO entries(
                    id, collection_id, path, schema_version, title, entry_type,
                    status, importance, scope, risk, durability, evidence,
                    created_at, updated_at, expires_at, summary, body,
                    content_hash, token_estimate
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    rid, cid, rel_path, int(meta.get("schema_version", 1)),
                    r["title"], str(meta["type"]), str(meta["status"]),
                    str(meta["importance"]), str(meta["scope"]), str(meta["risk"]),
                    str(meta["durability"]), str(meta["evidence"]),
                    str(meta["created_at"]), str(meta["updated_at"]), expires,
                    r["summary"], r["body"], content_hash(r["text"]),
                    token_estimate(r["body"]),
                ),
            )

            for topic in r["topics"]:
                key = topic.lower().strip().replace(" ", "-")
                cache_key = (cid, key)
                if cache_key not in topic_ids:
                    con.execute(
                        """INSERT OR IGNORE INTO topics(collection_id, topic_key, display_name)
                           VALUES (?,?,?)""",
                        (cid, key, topic),
                    )
                    row = con.execute(
                        "SELECT id FROM topics WHERE collection_id=? AND topic_key=?",
                        (cid, key),
                    ).fetchone()
                    topic_ids[cache_key] = int(row["id"])
                con.execute(
                    "INSERT OR IGNORE INTO entry_topics(entry_id, topic_id) VALUES (?,?)",
                    (rid, topic_ids[cache_key]),
                )

            # Identifier expansions go in the column they came from, so a name
            # in a title keeps title weight instead of being demoted to body.
            con.execute(
                "INSERT INTO entry_fts(entry_id, title, summary, body, topics) VALUES (?,?,?,?,?)",
                (rid,
                 r["title"] + " " + expand_identifiers(r["title"]),
                 r["summary"] + " " + expand_identifiers(r["summary"]),
                 r["body"] + " " + expand_identifiers(r["body"]),
                 " ".join(r["topics"])),
            )

            # One extra row per section, all carrying this record's id. Search
            # deduplicates by id, so these add reachability without adding
            # results: the record surfaces when any one of its findings
            # matches, instead of only when the document as a whole does.
            for heading, passage in split_sections(r["body"]):
                con.execute(
                    "INSERT INTO entry_fts(entry_id, title, summary, body, topics)"
                    " VALUES (?,?,?,?,?)",
                    (rid,
                     f'{r["title"]} {heading} {expand_identifiers(heading)}',
                     "",
                     passage + " " + expand_identifiers(passage),
                     " ".join(r["topics"]) + " " + SECTION_MARKER),
                )

        # Relations are inserted after every entry exists, so file ordering
        # cannot cause a spurious foreign-key failure. Targets that were skipped
        # as invalid are dropped rather than aborting the build.
        indexed_ids = {str(r["meta"]["id"]) for r in records}
        for r in records:
            rid = str(r["meta"]["id"])
            for rtype, targets in r["relations"].items():
                if rtype not in RELATION_TYPES:
                    continue
                for target in targets:
                    if target not in indexed_ids:
                        continue
                    con.execute(
                        """INSERT OR IGNORE INTO relations(
                               source_entry_id, target_entry_id, relation_type)
                           VALUES (?,?,?)""",
                        (rid, target, rtype),
                    )

        # Link topic summaries where their first topic matches the topic key.
        for r in records:
            if str(r["meta"].get("type")) == "topic_summary" and r["topics"]:
                key = r["topics"][0].lower().strip().replace(" ", "-")
                con.execute(
                    """UPDATE topics SET summary_entry_id=?
                       WHERE collection_id=? AND topic_key=?""",
                    (str(r["meta"]["id"]), col_ids[r["collection_root"]], key),
                )

        for key, value in (
            ("schema", "1"),
            ("lore_version", LORE_VERSION),
            ("skipped_count", str(len(errors))),
            ("indexed_count", str(len(records))),
            ("fingerprint", archive_fingerprint(root)),
            ("built_at", datetime.now().astimezone().replace(microsecond=0).isoformat()),
        ):
            con.execute("INSERT OR REPLACE INTO index_meta(key, value) VALUES (?,?)", (key, value))

        con.commit()
        for collection_root in collections:
            generate_index(root, con, col_ids[collection_root], collection_root)
        con.close()
        os.replace(staging, db)
    except BaseException:
        if con is not None:
            con.close()
        try:
            staging.unlink()
        except OSError:
            pass
        raise

    if not quiet:
        print(f"Rebuilt {display_path(root, db_path(root))} from {len(records)} "
              f"record(s) across {len(collections)} collection(s).")
    if errors:
        print(f"Skipped {len(errors)} invalid record(s); they are NOT searchable:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print("Run `lore validate` to gate on these.", file=sys.stderr)
    if warnings and not quiet:
        for w in warnings:
            print(f"warning: {w}", file=sys.stderr)

    return 1 if (strict and errors) else 0


def generate_index(root: Path, con: sqlite3.Connection, cid: str, collection_root: Path) -> None:
    rows = con.execute(
        """SELECT id,title,entry_type,status,importance,path
           FROM entries
           WHERE collection_id=? AND status NOT IN ('superseded','deprecated')
           ORDER BY
             CASE importance WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                             WHEN 'normal' THEN 2 ELSE 3 END,
             title COLLATE NOCASE""",
        (cid,),
    ).fetchall()
    topics = con.execute(
        """SELECT t.display_name, e.path AS summary_path
           FROM topics t
           LEFT JOIN entries e ON e.id=t.summary_entry_id
           WHERE t.collection_id=?
           ORDER BY t.display_name COLLATE NOCASE""",
        (cid,),
    ).fetchall()

    out = [
        "# Memory Index",
        "",
        "> Generated by `lore rebuild`. Do not edit manually.",
        "",
        "## Topics",
        "",
    ]
    if topics:
        for t in topics:
            if t["summary_path"]:
                out.append(f"- {t['display_name']} → `{t['summary_path']}`")
            else:
                out.append(f"- {t['display_name']}")
    else:
        out.append("- No indexed topics yet.")

    out += ["", "## Critical / High Current Knowledge", ""]
    important = [r for r in rows if r["importance"] in ("critical", "high")]
    if important:
        for r in important:
            out.append(f"- **{r['importance'].upper()}** - {r['title']} → `{r['path']}` (`{r['id']}`)")
    else:
        out.append("- No critical or high-priority records yet.")

    out += [
        "",
        "## Retrieval",
        "",
        "Search first; read full records selectively:",
        "",
        "```bash",
        'python tools/lore/lore.py search "<query>"',
        "python tools/lore/lore.py show <record-id>",
        "```",
        "",
    ]
    (collection_root / "memory" / "MEMORY_INDEX.md").write_text(
        "\n".join(out), encoding="utf-8", newline="\n")


def ensure_db(root: Path) -> sqlite3.Connection:
    """Open the index, building it if absent or stale.

    A validation problem never reaches the caller as a failure: rebuild skips
    the offending record and the remaining archive stays queryable.

    Staleness triggers a rebuild rather than a warning. A stale index answers
    "No matching record", which reads exactly like "this knowledge does not
    exist" - the one wrong answer a memory system must never give. A rebuild
    costs a fraction of a second per few hundred records, so correctness wins.
    """
    if not db_path(root).exists():
        rebuild(root, strict=False, quiet=True)
        return connect(root)

    con = connect(root)
    stored = read_meta(con, "fingerprint")
    schema = read_meta(con, "schema")
    lore_version = read_meta(con, "lore_version")
    current = archive_fingerprint(root)
    if schema != "1" or lore_version != LORE_VERSION or not stored or stored != current:
        con.close()
        if stored and stored != current:
            print("note: memory Markdown changed since the last build; reindexing.",
                  file=sys.stderr)
        elif lore_version and lore_version != LORE_VERSION:
            print(f"note: index was built by lore {lore_version}; reindexing.",
                  file=sys.stderr)
        rebuild(root, strict=False, quiet=True)
        return connect(root)
    return con


def read_meta(con: sqlite3.Connection, key: str, default: str = "") -> str:
    try:
        row = con.execute("SELECT value FROM index_meta WHERE key=?", (key,)).fetchone()
    except sqlite3.Error:
        return default
    return str(row["value"]) if row else default


def log_retrieval(root: Path, action: str, query: str, returned: list[str]) -> None:
    """Append one line per retrieval to .lore/retrieval.jsonl.

    Without this there is no way to answer the questions the migration plan
    says to measure: which records are ever returned, which returned records
    are ever opened, and how often a search finds nothing. An archive's
    characteristic failure is accumulating records nothing ever retrieves, and
    that failure is invisible unless retrieval is recorded.

    Local, derived, gitignored with the rest of `.lore/`, and never allowed
    to break a search: any failure here is silently ignored.
    """
    try:
        line = json.dumps({
            "at": datetime.now().astimezone().replace(microsecond=0).isoformat(),
            "action": action,
            "query": query,
            "returned": returned,
        }, ensure_ascii=False)
        path = root / ".lore" / "retrieval.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + chr(10))
    except OSError:
        pass


def warn_index_state(root: Path, con: sqlite3.Connection) -> None:
    """Fail-open must not mean fail-silent: say what is missing from the index.

    Staleness is handled by `ensure_db`, which reindexes rather than warning.
    What remains reportable is the records that are present on disk but could
    not be indexed, since a query will never return them.
    """
    skipped = read_meta(con, "skipped_count", "0")
    if skipped not in ("", "0"):
        print(
            f"note: {skipped} record(s) were excluded from this index because they are "
            f"invalid. Run `lore validate` to see them.",
            file=sys.stderr,
        )


# --------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------

def fts_query(text: str) -> tuple[str, set[str]]:
    words = QUERY_WORD_RE.findall(text.lower())
    words = [w for w in words if len(w) > 1]
    if not words:
        raise ValueError("query contains no searchable terms")
    escaped = [f'"{w.replace(chr(34), "")}"' for w in words]
    return " OR ".join(escaped), set(words)


def search(root: Path, query: str, history: bool, limit: int, scope: str | None,
           collection: str | None, log: bool = True,
           entry_type: str | None = None, topic: str | None = None,
           json_output: bool = False, status: str | None = None,
           importance: str | None = None) -> int:
    """Ranked search. `log=False` for internal callers.

    The retrieval log answers which records real work retrieves. `doctor` and
    `eval` issue hundreds of searches between them, and recording those would
    bury genuine traffic under tooling and make `lore usage` measure itself.
    """
    con = ensure_db(root)
    try:
        warn_index_state(root, con)
        try:
            fq, qwords = fts_query(query)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2

        params: list[Any] = [fq]
        if status:
            status_clause = "AND e.status = ?"
            params.append(status)
        else:
            status_clause = "" if history else "AND e.status NOT IN ('superseded','deprecated')"
        collection_clause = ""
        if collection:
            collection_clause = "AND c.name = ?"
            params.append(collection)
        type_clause = ""
        if entry_type:
            type_clause = "AND e.entry_type = ?"
            params.append(entry_type)
        importance_clause = ""
        if importance:
            importance_clause = "AND e.importance = ?"
            params.append(importance)
        topic_clause = ""
        if topic:
            topic_key = topic.lower().strip().replace(" ", "-")
            topic_clause = """AND EXISTS (
                SELECT 1 FROM entry_topics et_filter
                JOIN topics t_filter ON t_filter.id=et_filter.topic_id
                WHERE et_filter.entry_id=e.id AND lower(t_filter.topic_key)=lower(?)
            )"""
            params.append(topic_key)

        select = """SELECT e.*, c.name AS collection_name,
                           f.topics AS fts_topics, bm25(entry_fts, 0.0, 8.0, 6.0, 1.0, 3.0) AS bm
                    FROM entry_fts f
                    JOIN entries e ON e.id=f.entry_id
                    JOIN collections c ON c.id=e.collection_id
                    WHERE entry_fts MATCH ?"""

        # Pass 1: bounded relevance pool.
        relevance = con.execute(
            f"{select} {status_clause} {collection_clause} {type_clause} "
            f"{importance_clause} {topic_clause} "
            "ORDER BY bm25(entry_fts, 0.0, 8.0, 6.0, 1.0, 3.0) LIMIT ?",
            (*params, RELEVANCE_POOL),
        ).fetchall()

        # Pass 2: unbounded safety net. Critical records and critical invariants
        # that match the query are always candidates, whatever their bm25 rank.
        # Truncating the pool before this check meant the "always surfaces"
        # guarantee quietly stopped holding as the archive grew.
        safety = con.execute(
            f"""{select} {status_clause} {collection_clause} {type_clause}
                {importance_clause} {topic_clause}
                AND (e.importance='critical' OR (e.risk='critical' AND e.durability='invariant'))""",
            tuple(params),
        ).fetchall()

        # Every candidate row, not one per record. A record indexed both whole
        # and by section contributes several rows here and they do not score
        # alike, so the choice between them is deferred until after scoring.
        # Duplicates are harmless: the collapse below keeps the best.
        rows = [*relevance, *safety]

        if not rows:
            # An empty result must not read like "this knowledge does not
            # exist". Say how much was actually searched and what vocabulary
            # the archive uses, so the agent can tell a real absence from a
            # wording miss and retry with the archive's own terms.
            total = con.execute(
                f"""SELECT COUNT(*) n FROM entries e
                    JOIN collections c ON c.id=e.collection_id
                    WHERE 1=1 {status_clause} {collection_clause} {type_clause}
                    {importance_clause} {topic_clause}""",
                tuple(params[1:]),
            ).fetchone()["n"]
            # Busiest topics first, not alphabetical: the point is to show the
            # vocabulary the archive actually uses, and the first 15 by
            # alphabet are a random sample of it.
            topic_base = f"""FROM topics t
                JOIN entry_topics et ON et.topic_id=t.id
                JOIN entries e ON e.id=et.entry_id
                JOIN collections c ON c.id=e.collection_id
                WHERE 1=1 {status_clause} {collection_clause} {type_clause}
                {importance_clause} {topic_clause}"""
            filter_params = tuple(params[1:])
            topics = [r["topic_key"] for r in con.execute(
                f"""SELECT t.topic_key, COUNT(DISTINCT et.entry_id) n {topic_base}
                    GROUP BY t.topic_key ORDER BY n DESC, t.topic_key LIMIT 15""",
                filter_params,
            ).fetchall()]
            ntopics = con.execute(
                f"SELECT COUNT(DISTINCT t.topic_key) n {topic_base}", filter_params
            ).fetchone()["n"]
            if json_output:
                print(json.dumps({
                    "query": query,
                    "filters": {
                        "history": history, "scope": scope, "collection": collection,
                        "type": entry_type, "topic": topic, "status": status,
                        "importance": importance,
                    },
                    "count": 0,
                    "searched": total,
                    "suggested_topics": topics,
                    "results": [],
                }, ensure_ascii=False, indent=2))
            else:
                print(f"No matching record. Searched {total} record(s).")
                if topics:
                    more = f", +{ntopics - len(topics)} more" if ntopics > len(topics) else ""
                    print(f"Busiest topics: {', '.join(topics)}{more}")
                    print("If the answer should exist, retry using the archive's own terms.")
            if log:
                log_retrieval(root, "search", query, [])
            return 0

        # Normalise bm25 (more negative is a better match) onto 0..TEXT_WEIGHT
        # across the whole candidate set, so textual relevance keeps its
        # resolution instead of flattening to zero past an arbitrary rank.
        strengths = [-float(r["bm"]) for r in rows]
        lo, hi = min(strengths), max(strengths)
        span = hi - lo

        ranked = []
        for row, strength in zip(rows, strengths):
            text_score = TEXT_WEIGHT if span <= 0 else TEXT_WEIGHT * (strength - lo) / span
            topics = {x.lower() for x in str(row["fts_topics"]).split()}
            from_section = SECTION_MARKER in topics
            topics.discard(SECTION_MARKER)
            topic_bonus = min(TOPIC_BOOST_CAP, len(qwords & topics) * TOPIC_BOOST_PER_HIT)
            score = (
                text_score
                + topic_bonus
                + IMPORTANCE_BOOST[row["importance"]]
                + RISK_BOOST[row["risk"]]
                + DURABILITY_BOOST[row["durability"]]
                + STATUS_BOOST[row["status"]]
                + EVIDENCE_BOOST[row["evidence"]]
            )
            if scope and row["scope"] == scope:
                score += SCOPE_MATCH_BOOST
            if from_section:
                score -= SECTION_PENALTY

            # A caution marker for display only. It no longer reorders results:
            # a critical record has to earn its rank on relevance plus weight,
            # instead of pre-empting every better match in the list.
            hard = (
                row["importance"] == "critical"
                or (row["risk"] == "critical" and row["durability"] == "invariant")
            )
            ranked.append((score, hard, row))

        # Collapse to one entry per record only now that scores exist. A record
        # can be indexed both whole and by section, and those two rows do not
        # score alike: the section row pays SECTION_PENALTY. Choosing the
        # survivor by bm25 alone discarded the whole-record row whenever a
        # section merely tied it, and the record then paid a penalty it had not
        # earned. On tied bm25 values that choice came down to SQLite row
        # order, so a record could fall out of the results on a coin flip.
        best: dict[str, tuple] = {}
        for item in ranked:
            rid = str(item[2]["id"])
            if rid not in best or item[0] > best[rid][0]:
                best[rid] = item
        ranked = list(best.values())

        ranked.sort(key=lambda x: (-x[0], x[2]["title"].lower()))
        ranked = ranked[:limit]

        multi = con.execute("SELECT COUNT(*) c FROM collections").fetchone()["c"] > 1

        if json_output:
            results = []
            for score, hard, r in ranked:
                topics = [row["display_name"] for row in con.execute(
                    """SELECT t.display_name FROM topics t
                       JOIN entry_topics et ON et.topic_id=t.id
                       WHERE et.entry_id=? ORDER BY t.display_name COLLATE NOCASE""",
                    (r["id"],),
                ).fetchall()]
                location = f"{r['collection_name']}/{r['path']}" if multi else r["path"]
                results.append({
                    "id": r["id"], "title": r["title"], "type": r["entry_type"],
                    "status": r["status"], "importance": r["importance"],
                    "scope": r["scope"], "risk": r["risk"],
                    "durability": r["durability"], "evidence": r["evidence"],
                    "topics": topics, "collection": r["collection_name"],
                    "path": location, "token_estimate": r["token_estimate"],
                    "score": round(score, 2), "critical": hard,
                    "summary": " ".join(str(r["summary"]).split()),
                })
            print(json.dumps({
                "query": query,
                "filters": {
                    "history": history, "scope": scope, "collection": collection,
                    "type": entry_type, "topic": topic, "status": status,
                    "importance": importance,
                },
                "count": len(results),
                "results": results,
            }, ensure_ascii=False, indent=2))
        else:
            for i, (score, hard, r) in enumerate(ranked, 1):
                marker = " !" if hard else ""
                print(
                    f"{i}. [{r['importance'].upper()} | {r['status']} | {r['evidence']}]"
                    f"{marker} {r['title']}"
                )
                print(f"   id: {r['id']}")
                location = f"{r['collection_name']}/{r['path']}" if multi else r["path"]
                print(f"   path: {location}")
                print(
                    f"   scope={r['scope']} risk={r['risk']} durability={r['durability']} "
                    f"~{r['token_estimate']} tokens score={score:.0f}"
                )
                summary = " ".join(str(r["summary"]).split())
                if len(summary) > 360:
                    summary = summary[:357] + "..."
                print(f"   {summary}")
                print()
        if log:
            log_retrieval(root, "search", query, [str(r["id"]) for _, _, r in ranked])
        return 0
    finally:
        con.close()


def show(root: Path, rid: str, json_output: bool = False) -> int:
    con = ensure_db(root)
    try:
        warn_index_state(root, con)
        row = con.execute(
            """SELECT e.*, c.name AS collection_name, c.root_path FROM entries e
               JOIN collections c ON c.id=e.collection_id WHERE e.id=?""",
            (rid,),
        ).fetchone()
        if not row:
            print(f"Unknown record id: {rid}", file=sys.stderr)
            return 1
        if json_output:
            topics = [item["display_name"] for item in con.execute(
                """SELECT t.display_name FROM topics t
                   JOIN entry_topics et ON et.topic_id=t.id
                   WHERE et.entry_id=? ORDER BY t.display_name COLLATE NOCASE""",
                (rid,),
            ).fetchall()]
            relations: dict[str, list[str]] = {}
            for item in con.execute(
                """SELECT relation_type, target_entry_id FROM relations
                   WHERE source_entry_id=? ORDER BY relation_type, target_entry_id""",
                (rid,),
            ).fetchall():
                relations.setdefault(str(item["relation_type"]), []).append(
                    str(item["target_entry_id"])
                )
            payload = {
                "schema_version": row["schema_version"], "id": row["id"],
                "title": row["title"], "type": row["entry_type"],
                "status": row["status"], "importance": row["importance"],
                "scope": row["scope"], "risk": row["risk"],
                "durability": row["durability"], "evidence": row["evidence"],
                "topics": topics, "created_at": row["created_at"],
                "updated_at": row["updated_at"], "expires_at": row["expires_at"],
                "relations": relations, "collection": row["collection_name"],
                "path": row["path"], "token_estimate": row["token_estimate"],
                "summary": row["summary"], "body": row["body"],
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print((Path(row["root_path"]) / row["path"]).read_text(encoding="utf-8"))
        log_retrieval(root, "show", rid, [rid])
        return 0
    finally:
        con.close()


def list_records(root: Path, history: bool, limit: int, entry_type: str | None,
                 topic: str | None, collection: str | None,
                 json_output: bool = False, status: str | None = None) -> int:
    """Browse record metadata without requiring a full-text query."""
    con = ensure_db(root)
    try:
        warn_index_state(root, con)
        clauses = []
        params: list[Any] = []
        if status:
            clauses.append("e.status = ?")
            params.append(status)
        elif not history:
            clauses.append("e.status NOT IN ('superseded','deprecated')")
        if entry_type:
            clauses.append("e.entry_type = ?")
            params.append(entry_type)
        if topic:
            clauses.append("""EXISTS (
                SELECT 1 FROM entry_topics et_filter
                JOIN topics t_filter ON t_filter.id=et_filter.topic_id
                WHERE et_filter.entry_id=e.id AND t_filter.topic_key=?
            )""")
            params.append(topic.lower().strip().replace(" ", "-"))
        if collection:
            clauses.append("c.name = ?")
            params.append(collection)
        where = " AND ".join(clauses) if clauses else "1=1"
        base = f"""FROM entries e
            JOIN collections c ON c.id=e.collection_id
            WHERE {where}"""
        total = con.execute(f"SELECT COUNT(*) n {base}", tuple(params)).fetchone()["n"]
        rows = con.execute(
            f"""SELECT e.*, c.name AS collection_name {base}
                ORDER BY e.title COLLATE NOCASE, e.id LIMIT ?""",
            (*params, limit),
        ).fetchall()
        records = []
        for row in rows:
            topics = [item["display_name"] for item in con.execute(
                """SELECT t.display_name FROM topics t
                   JOIN entry_topics et ON et.topic_id=t.id
                   WHERE et.entry_id=? ORDER BY t.display_name COLLATE NOCASE""",
                (row["id"],),
            ).fetchall()]
            records.append({
                "id": row["id"], "title": row["title"],
                "type": row["entry_type"], "status": row["status"],
                "importance": row["importance"], "scope": row["scope"],
                "risk": row["risk"], "durability": row["durability"],
                "evidence": row["evidence"], "topics": topics,
                "collection": row["collection_name"], "path": row["path"],
                "token_estimate": row["token_estimate"],
                "updated_at": row["updated_at"], "summary": row["summary"],
            })
        if json_output:
            print(json.dumps({
                "filters": {
                    "history": history, "type": entry_type,
                    "topic": topic, "collection": collection, "status": status,
                },
                "count": total, "returned": len(records), "records": records,
            }, ensure_ascii=False, indent=2))
        else:
            multi = con.execute("SELECT COUNT(*) c FROM collections").fetchone()["c"] > 1
            print(f"{total} record(s); showing {len(records)}.")
            for index, record in enumerate(records, 1):
                print(
                    f"{index}. [{record['type']} | {record['importance']} | "
                    f"{record['status']}] {record['title']}"
                )
                print(f"   id: {record['id']}")
                location = (f"{record['collection']}/{record['path']}"
                            if multi else record["path"])
                print(f"   path: {location}")
                if record["topics"]:
                    print(f"   topics: {', '.join(record['topics'])}")
                print(f"   {' '.join(str(record['summary']).split())}")
                print()
        return 0
    finally:
        con.close()


def list_topics(root: Path, limit: int, collection: str | None,
                json_output: bool = False) -> int:
    """Browse the active topic vocabulary, busiest first."""
    con = ensure_db(root)
    try:
        warn_index_state(root, con)
        collection_clause = "AND c.name = ?" if collection else ""
        params: tuple[Any, ...] = (collection,) if collection else ()
        base = f"""FROM topics t
            JOIN collections c ON c.id=t.collection_id
            JOIN entry_topics et ON et.topic_id=t.id
            JOIN entries e ON e.id=et.entry_id
            WHERE e.status NOT IN ('superseded','deprecated') {collection_clause}"""
        total = con.execute(
            f"""SELECT COUNT(*) n FROM (
                SELECT t.id {base} GROUP BY t.id
            )""", params,
        ).fetchone()["n"]
        rows = con.execute(
            f"""SELECT t.topic_key, t.display_name, c.name AS collection_name,
                       COUNT(et.entry_id) AS record_count
                {base}
                GROUP BY t.id
                ORDER BY record_count DESC, t.display_name COLLATE NOCASE,
                         c.name COLLATE NOCASE
                LIMIT ?""",
            (*params, limit),
        ).fetchall()
        topics = [{
            "key": row["topic_key"], "name": row["display_name"],
            "collection": row["collection_name"], "record_count": row["record_count"],
        } for row in rows]
        if json_output:
            print(json.dumps({
                "collection": collection, "count": total,
                "returned": len(topics), "topics": topics,
            }, ensure_ascii=False, indent=2))
        else:
            print(f"{total} active topic(s); showing {len(topics)}.")
            multi = con.execute("SELECT COUNT(*) c FROM collections").fetchone()["c"] > 1
            for index, topic_row in enumerate(topics, 1):
                location = (f" [{topic_row['collection']}]" if multi else "")
                print(
                    f"{index}. {topic_row['name']}{location} — "
                    f"{topic_row['record_count']} record(s)"
                )
        return 0
    finally:
        con.close()


def list_collections(root: Path, json_output: bool = False) -> int:
    """Describe every indexed collection and its archive footprint."""
    con = ensure_db(root)
    try:
        warn_index_state(root, con)
        rows = con.execute(
            """SELECT c.name, c.kind,
                      (SELECT COUNT(*) FROM entries e
                       WHERE e.collection_id=c.id) AS record_count,
                      (SELECT COUNT(*) FROM entries e
                       WHERE e.collection_id=c.id
                         AND e.status NOT IN ('superseded','deprecated'))
                         AS active_record_count,
                      (SELECT COUNT(*) FROM topics t
                       WHERE t.collection_id=c.id) AS topic_count
               FROM collections c
               ORDER BY c.name COLLATE NOCASE"""
        ).fetchall()
        collections = [{
            "name": row["name"], "kind": row["kind"],
            "record_count": row["record_count"],
            "active_record_count": row["active_record_count"],
            "topic_count": row["topic_count"],
        } for row in rows]
        if json_output:
            print(json.dumps({
                "count": len(collections), "collections": collections,
            }, ensure_ascii=False, indent=2))
        else:
            print(f"{len(collections)} collection(s).")
            for index, item in enumerate(collections, 1):
                print(f"{index}. {item['name']} [{item['kind']}]")
                print(
                    f"   {item['active_record_count']} active / "
                    f"{item['record_count']} total record(s); "
                    f"{item['topic_count']} topic(s)"
                )
        return 0
    finally:
        con.close()


def usage(root: Path) -> int:
    """Report what retrieval actually did, from .lore/retrieval.jsonl.

    The question that decides whether an archive is earning its keep is not
    how many records it holds, it is how many of them anything has ever
    retrieved. A record nothing returns costs tokens to write, adds noise to
    every ranking afterwards, and has never once been useful. Without this
    command the log is write-only and that question stays unanswerable.
    """
    log = root / ".lore" / "retrieval.jsonl"
    if not log.exists():
        print("No retrieval log yet. It is written by `lore search` and `lore show`.")
        return 0

    searches = 0
    empty = 0
    returned: dict[str, int] = {}
    opened: dict[str, int] = {}
    empty_queries: list[str] = []
    for line in log.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("action") == "search":
            searches += 1
            hits = rec.get("returned") or []
            if not hits:
                empty += 1
                empty_queries.append(str(rec.get("query", "")))
            for rid in hits:
                returned[rid] = returned.get(rid, 0) + 1
        elif rec.get("action") == "show":
            for rid in rec.get("returned") or []:
                opened[rid] = opened.get(rid, 0) + 1

    con = ensure_db(root)
    try:
        all_ids = [str(r["id"]) for r in con.execute("SELECT id FROM entries").fetchall()]
        titles = {str(r["id"]): str(r["title"])
                  for r in con.execute("SELECT id, title FROM entries").fetchall()}
    finally:
        con.close()

    never = [i for i in all_ids if i not in returned]
    surfaced_never_opened = [i for i in returned if i not in opened]

    print(f"searches: {searches}")
    if searches:
        print(f"found nothing: {empty} ({empty / searches:.0%})")
    print(f"records: {len(all_ids)}")
    print(f"never returned by any search: {len(never)}")
    print(f"returned but never opened: {len(surfaced_never_opened)}")

    if returned:
        print()
        print("most returned:")
        for rid, n in sorted(returned.items(), key=lambda x: -x[1])[:8]:
            mark = "" if rid in opened else "   (never opened)"
            print(f"  {n:>3}x {titles.get(rid, rid)}{mark}")

    # A never-retrieved list is only meaningful once enough searching has
    # happened to make absence evidence rather than earliness. Twenty searches
    # in, "nothing has returned this" still mostly means "nobody has asked
    # about it yet", and calling that dead weight would retire useful records
    # on no evidence.
    if never and len(all_ids) >= 10 and searches >= EVIDENCE_THRESHOLD:
        print()
        print(f"never retrieved ({len(never)} of {len(all_ids)}) after {searches} searches:")
        for rid in never[:12]:
            print(f"  - {titles.get(rid, rid)}")
        if len(never) > 12:
            print(f"  ... and {len(never) - 12} more")
        print()
        print("Candidates for dead weight. Either the knowledge was not worth")
        print("keeping, or it is worded in terms nobody searches for. Both are")
        print("worth knowing; neither is visible from the record itself.")
    elif never and searches < EVIDENCE_THRESHOLD:
        print()
        print(f"{len(never)} record(s) not yet returned by any search. Too early to")
        print(f"read anything into that: come back after {EVIDENCE_THRESHOLD} searches "
              f"(you have {searches}).")

    if empty_queries:
        print()
        print("searches that found nothing:")
        for q in empty_queries[-8:]:
            print(f"  - {q}")

    return 0


def _eval_path(root: Path) -> Path:
    return root / "eval" / "queries.jsonl"


def _eval_runs_dir(root: Path) -> Path:
    """Saved eval runs live beside the queries, not under .lore/.

    A baseline is a measurement record, not derived state. Keeping it in
    .lore/ meant any rebuild or reset destroyed the thing you were measuring
    against, which defeats the point of saving it. This directory is meant to
    be kept, and committed if the archive is.
    """
    return root / "eval" / "runs"


def _run_eval(root: Path, cases: list[dict]) -> list[dict]:
    """Search once per case and record where the expected record landed."""
    import io
    from contextlib import redirect_stdout, redirect_stderr

    results = []
    for case in cases:
        query = str(case.get("q", ""))
        expect = case.get("expect") or []
        if isinstance(expect, str):
            expect = [expect]
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(io.StringIO()):
            search(root, query, history=False, limit=10, scope=None,
                   collection=None, log=False)
        ids = re.findall(r"^   id: (\S+)", buf.getvalue(), re.M)
        rank = 0
        for i, rid in enumerate(ids, 1):
            if rid in expect:
                rank = i
                break
        results.append({"q": query, "expect": expect, "rank": rank, "got": ids[:5]})
    return results


def _eval_scores(results: list[dict]) -> dict:
    n = len(results) or 1
    out = {}
    for k in (1, 3, 5):
        out[f"recall@{k}"] = sum(1 for r in results if r["rank"] and r["rank"] <= k) / n
    out["mrr"] = sum(1 / r["rank"] for r in results if r["rank"]) / n
    return out


def evaluate(root: Path, save: str | None, against: str | None) -> int:
    """Measure retrieval against a set of queries with known correct answers.

    This is a regression harness, not an unbiased benchmark. The queries are
    written by whoever knows the archive, so the absolute numbers flatter it.
    What it measures honestly is *change*: whether an edit to ranking, a
    schema change, or a week of new records made retrieval better or worse on
    questions that actually matter. That is the number worth tracking.

    Add a case every time retrieval disappoints you in real work. A query that
    should have found something and did not is the most valuable row in the
    file, and it costs one line to record while the disappointment is fresh.
    """
    path = _eval_path(root)
    if not path.exists():
        print(f"No eval set at {display_path(root, path)}.")
        print()
        print("Create it with one JSON object per line:")
        print('  {"q": "a question you would really ask", "expect": ["<record-id>"]}')
        print()
        print("`expect` may list several ids if more than one answer is acceptable.")
        return 0

    cases = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            cases.append(json.loads(line))
        except ValueError as e:
            print(f"{display_path(root, path)}:{i}: not valid JSON ({e})", file=sys.stderr)
            return 1
    if not cases:
        print("Eval set is empty.")
        return 0

    results = _run_eval(root, cases)
    scores = _eval_scores(results)

    # Attribute each query to the collection its ANSWER lives in, so a total
    # miss still counts against the right collection.
    con = ensure_db(root)
    try:
        home = {str(r["id"]): str(r["coll"]) for r in con.execute(
            """SELECT e.id, c.name AS coll FROM entries e
               JOIN collections c ON c.id=e.collection_id""")}
    finally:
        con.close()
    for r in results:
        r["coll"] = next((home[i] for i in r["expect"] if i in home), "?")

    prior = None
    if against:
        ap = _eval_runs_dir(root) / f"{against}.json"
        if not ap.exists():
            print(f"No saved run named '{against}'. Saved runs: "
                  f"{', '.join(sorted(p.stem for p in _eval_runs_dir(root).glob('*.json'))) or 'none'}",
                  file=sys.stderr)
            return 1
        prior = json.loads(ap.read_text(encoding="utf-8"))
        prior_ranks = {r["q"]: r["rank"] for r in prior["results"]}

    print(f"{'rank':>5}  {'was':>4}  query")
    regressions = 0
    for r in results:
        rank = r["rank"] or 0
        shown = str(rank) if rank else "-"
        was = ""
        if prior:
            pr = prior_ranks.get(r["q"])
            if pr is not None:
                was = str(pr) if pr else "-"
                worse = (pr and rank and rank > pr) or (pr and not rank)
                if worse:
                    regressions += 1
                    shown += " !"
        print(f"{shown:>5}  {was:>4}  {r['q'][:58]}")

    print()
    line = "  ".join(f"{k} {v:.0%}" for k, v in scores.items() if k != "mrr")
    print(f"{line}  MRR {scores['mrr']:.2f}   ({len(results)} queries)")

    by_coll: dict[str, list] = {}
    for r in results:
        by_coll.setdefault(r["coll"], []).append(r)
    if len(by_coll) > 1:
        print()
        print(f"  {'collection':<20}{'n':>4}{'r@1':>7}{'r@3':>7}{'r@5':>7}{'MRR':>7}")
        for coll, group in sorted(by_coll.items()):
            s = _eval_scores(group)
            print(f"  {coll:<20}{len(group):>4}{s['recall@1']:>7.0%}"
                  f"{s['recall@3']:>7.0%}{s['recall@5']:>7.0%}{s['mrr']:>7.2f}")

    if prior:
        ps = prior["scores"]
        deltas = []
        for k in ("recall@1", "recall@3", "recall@5"):
            d = scores[k] - ps[k]
            deltas.append(f"{k} {d:+.0%}")
        print(f"vs '{against}':  " + "  ".join(deltas) +
              f"  MRR {scores['mrr'] - ps['mrr']:+.2f}")
        if regressions:
            print(f"\n{regressions} quer(y/ies) ranked worse than '{against}', marked !")

    if save:
        out = _eval_runs_dir(root) / f"{save}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(
            {"saved_at": datetime.now().astimezone().replace(microsecond=0).isoformat(),
             "scores": scores, "results": results}, indent=2), encoding="utf-8")
        print(f"\nSaved as '{save}'. Compare later with: lore eval --against {save}")

    return 1 if (prior and regressions) else 0


def doctor(root: Path, limit: int | None) -> int:
    """Health checks that need no hand-written ground truth.

    Findability: query each record by its own title and see whether it comes
    back first. A record that loses to something else on its own title is
    effectively invisible, because a real question about its subject will use
    fewer of its exact words, not more. The record that beat it is named, so
    the fix is a concrete edit rather than a global knob.

    Also flags summaries too thin to rank on, summaries that only restate the
    title, and records so large they behave like several.
    """
    import io
    from contextlib import redirect_stdout, redirect_stderr

    con = ensure_db(root)
    try:
        rows = con.execute(
            """SELECT e.id, e.title, e.summary, e.token_estimate, c.name AS coll
               FROM entries e JOIN collections c ON c.id=e.collection_id
               WHERE e.status NOT IN ('superseded','deprecated')
               ORDER BY c.name, e.title"""
        ).fetchall()
    finally:
        con.close()

    if not rows:
        print("No records to check.")
        return 0

    records = [dict(r) for r in rows]
    if limit:
        records = records[:limit]

    unfindable = []
    thin = []
    echo = []
    huge = []

    for r in records:
        summary = " ".join(str(r["summary"]).split())
        title = str(r["title"])

        if len(summary) < 60:
            thin.append((r, len(summary)))
        elif summary.lower().rstrip(".").strip() == title.lower().rstrip(".").strip():
            echo.append(r)
        if r["token_estimate"] and r["token_estimate"] > 2500:
            huge.append(r)

        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(io.StringIO()):
            try:
                search(root, title, history=False, limit=3, scope=None,
                       collection=None, log=False)
            except Exception:
                continue
        ids = re.findall(r"^   id: (\S+)", buf.getvalue(), re.M)
        if not ids:
            unfindable.append((r, None))
        elif ids[0] != r["id"]:
            titles = re.findall(r"^1\. \[[^\]]*\]\s*!?\s*(.+)$", buf.getvalue(), re.M)
            unfindable.append((r, titles[0] if titles else ids[0]))

    n = len(records)
    found = n - len(unfindable)
    print(f"findability: {found}/{n} records are returned first for their own title "
          f"({found/n:.0%})")
    print(f"thin summaries (under 60 chars): {len(thin)}")
    print(f"summaries that only restate the title: {len(echo)}")
    print(f"records over 2500 tokens: {len(huge)}")

    if unfindable:
        print()
        print("NOT FINDABLE BY THEIR OWN SUBJECT")
        print("These lose to another record on their own title, so a real question")
        print("phrased differently will not reach them. Sharpen the summary, or")
        print("check whether the winner has swallowed this record's subject.")
        print()
        for r, beaten_by in unfindable[:25]:
            print(f"  {r['coll']}/{r['title'][:58]}")
            print(f"     beaten by: {beaten_by or '(no results at all)'}")
        if len(unfindable) > 25:
            print(f"  ... and {len(unfindable) - 25} more")

    if thin:
        print()
        print("THIN SUMMARIES")
        print("The summary is the retrieval surface and carries 4x the weight of")
        print("the body. Too little text there and the record ranks on nothing.")
        print()
        for r, ln in thin[:12]:
            print(f"  {r['coll']}/{r['title'][:52]}  ({ln} chars)")
        if len(thin) > 12:
            print(f"  ... and {len(thin) - 12} more")

    if echo:
        print()
        print("SUMMARY ONLY RESTATES THE TITLE")
        for r in echo[:10]:
            print(f"  {r['coll']}/{r['title'][:58]}")
        if len(echo) > 10:
            print(f"  ... and {len(echo) - 10} more")

    if huge:
        print()
        print(f"LARGE ({len(huge)} records over 2500 tokens)")
        print("Informational, not a defect. Sections are indexed separately, so a")
        print("question about a record's fourth finding still reaches it: measured")
        print("82% of internal findings reachable, against 36% when only whole")
        print("records were indexed. Split only if a record covers subjects that")
        print("genuinely do not belong together.")
        print()
        for r in sorted(huge, key=lambda x: -x["token_estimate"])[:10]:
            print(f"  {r['token_estimate']:>6} tok  {r['coll']}/{r['title'][:48]}")

    return 0


def obsidian(root: Path) -> int:
    """Generate Obsidian navigation notes beside the archive.

    Writes to the archive root, never into `memory/`, so nothing generated
    here is ever indexed as a record. Safe to re-run; it overwrites its own
    output and touches nothing else.
    """
    con = ensure_db(root)
    try:
        rows = con.execute(
            """SELECT e.id, e.title, e.path, e.summary, e.importance, e.status,
                      e.entry_type, c.name AS coll, c.root_path
               FROM entries e JOIN collections c ON c.id=e.collection_id
               ORDER BY e.title"""
        ).fetchall()
        topic_rows = con.execute(
            """SELECT t.topic_key, e.id, e.title, e.path, c.name AS coll
               FROM topics t
               JOIN entry_topics et ON et.topic_id=t.id
               JOIN entries e ON e.id=et.entry_id
               JOIN collections c ON c.id=e.collection_id
               ORDER BY t.topic_key, e.title"""
        ).fetchall()
    finally:
        con.close()

    if not rows:
        print("Nothing to generate: the index is empty.")
        return 0

    def note_name(path: str) -> str:
        return Path(path).stem

    topics: dict[str, list] = {}
    for r in topic_rows:
        topics.setdefault(str(r["topic_key"]), []).append(r)

    hub_dir = root / "_topics"
    hub_dir.mkdir(parents=True, exist_ok=True)
    for existing in hub_dir.glob("*.md"):
        existing.unlink()

    for topic, entries in sorted(topics.items()):
        lines = [f"# {topic}", "",
                 f"{len(entries)} record(s) tagged `{topic}`.", ""]
        by_coll: dict[str, list] = {}
        for e in entries:
            by_coll.setdefault(str(e["coll"]), []).append(e)
        for coll, items in sorted(by_coll.items()):
            lines.append(f"## {coll}")
            lines.append("")
            for e in items:
                lines.append(f"- [[{note_name(str(e['path']))}|{e['title']}]]")
            lines.append("")
        (hub_dir / f"{topic}.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")

    by_coll_count: dict[str, int] = {}
    for r in rows:
        by_coll_count[str(r["coll"])] = by_coll_count.get(str(r["coll"]), 0) + 1

    critical = [r for r in rows if r["importance"] == "critical"]
    retired = [r for r in rows if r["status"] in RETIRED_STATUSES]

    home = ["# Lore", "",
            f"{len(rows)} records across {len(by_coll_count)} collection(s).", "",
            "## Collections", ""]
    for coll, n in sorted(by_coll_count.items()):
        home.append(f"- **{coll}** - {n} record(s)")
    home += ["", "## Always relevant", ""]
    if critical:
        for r in critical:
            home.append(f"- [[{note_name(str(r['path']))}|{r['title']}]]")
    else:
        home.append("_No records are marked critical._")
    home += ["", "## Topics", ""]
    for topic, entries in sorted(topics.items(), key=lambda x: (-len(x[1]), x[0])):
        home.append(f"- [[{topic}]] ({len(entries)})")
    if retired:
        home += ["", "## Retired", "",
                 "Excluded from normal search; kept for history.", ""]
        for r in retired:
            home.append(f"- [[{note_name(str(r['path']))}|{r['title']}]]")
    home += ["", "---", "",
             "Generated by `lore obsidian`. Edits here are overwritten.",
             "Canonical records live under each collection's `memory/`."]
    (root / "HOME.md").write_text("\n".join(home), encoding="utf-8", newline="\n")

    print(f"wrote HOME.md and {len(topics)} topic hub(s) in {display_path(root, hub_dir)}")
    print()
    print("Open the archive as a vault: Obsidian > Open folder as vault >")
    print(f"  {root}")
    print("Then open HOME.md. Graph view will show topic hubs as cluster centres.")
    print()
    print("Generated notes sit outside memory/, so lore never indexes them.")
    return 0


# A correction is announced, not mentioned. Matching the words alone flagged
# 102 of 293 records, because "turned out" and "update:" occur in any long
# engineering body. Real corrections are shouted: capitals, at the start of a
# line or in a heading. Matching the convention makes the check precise.
# Longest inflection first: alternation is ordered, so a bare UPDATE
# would match inside UPDATED and leave \\b to fail on the following D.
_MARKERS = (r"CORRECTED|CORRECTION|CORRECTS|RETRACTION|RETRACTED|"
            r"SUPERSEDED|SUPERSEDES|OUTDATED|NO LONGER TRUE|OBSOLETE|"
            r"UPDATED|UPDATE")

# In the body, a correction is ANNOUNCED: at the start of a line, in capitals,
# and either dated or introduced with a colon. The date-or-colon requirement is
# what separates "CORRECTED 2026-08-21:" from "UPDATE 40, OS 28, BLOATWARE 16",
# a category histogram, and from "**SUPERSEDED** (banners + struck-through
# titles)", which describes contract-status UI. Both were false positives on a
# real archive; domain vocabulary collides with correction vocabulary far more
# often than it looks like it should.
CORRECTION_RE = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]*)?\**[ \t]*(?:" + _MARKERS + r")\b"
    r"[ \t]*(?:\*{0,2}[ \t]*)(?::|\d{4}-\d{2}-\d{2}|\bon\b|\bby\b)",
    re.M)

# In the summary, a MENTION anywhere counts. A summary is a paragraph, so an
# author who wrote "... contradicts this. CORRECTED 2026-08-21" has carried
# the correction even though it is not at the start of a line.
SUMMARY_MENTION_RE = re.compile(r"(?:" + _MARKERS + r")\b", re.I)
# A record declaring ITSELF stale announces it: capitals, start of line,
# dated or introduced with a colon. Matching the bare word instead caught the
# subject matter every time, because in an engineering archive the vocabulary
# of staleness IS the domain vocabulary: `ContractStatus.Superseded` is an
# enum value, "the superseded push-registration model" is an adjective, and
# both records were current. Third occurrence of this class; the pattern, not
# the word list, is what needed fixing.
DECLARED_STALE_RE = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]*)?\**[ \t]*"
    r"(?:SUPERSEDED|OUTDATED|OBSOLETE|DEPRECATED|DO NOT USE|NO LONGER APPLIES)"
    r"\b[ \t]*\**[ \t]*(?::|\d{4}-\d{2}-\d{2}|\bby\b|\bin favour\b|$)",
    re.M)

# Counter-signals. A record can announce that it is stale and still be the
# live answer: an instructive failure kept on purpose, or a headline that
# aged while the method below it did not. Retiring those removes working
# knowledge from every default search.
KEPT_ON_PURPOSE = ("kept for", "keeping for", "for the history", "for history",
                   "still true", "still applies", "still valid", "still the",
                   "kept because", "retained for", "instructive")

# Tokens too common in one archive to signal a shared subject.
_DUP_STOP = {"the", "and", "for", "that", "with", "from", "not", "are", "was",
             "this", "but", "its", "has", "have", "all", "one", "can", "when",
             "what", "which", "into", "than", "then", "does", "did", "you",
             "your", "our", "their", "them", "they", "it", "is", "of", "to",
             "in", "on", "a", "an", "by", "at", "be", "as", "or", "if", "so"}


def _dup_tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower())
            if len(w) > 3 and w not in _DUP_STOP}


def conflicts(root: Path, threshold: float) -> int:
    """Report records that contradict each other or themselves.

    Nothing here is applied automatically, deliberately. An earlier version
    auto-retired records whose text announced they were stale; measured
    against a real archive it was wrong on two of four, because a record can
    say "SUPERSEDED" and still be the live answer ("OUTDATED HEADLINE, KEPT
    FOR THE HISTORY", "superseded ... still true: no other method works").

    The difference is authorial intent, which no pattern recovers. Retiring
    such a record removes it from every default search silently, which is the
    precise failure this system exists to prevent, so the tool finds and
    explains and a person decides.
    """
    con = ensure_db(root)
    try:
        rows = con.execute(
            """SELECT e.id, e.title, e.summary, e.body, e.status, e.path,
                      c.name AS coll, c.root_path
               FROM entries e JOIN collections c ON c.id=e.collection_id
               ORDER BY c.name, e.title"""
        ).fetchall()
        # Any relation at all means a person has already looked at this pair.
        linked: set[frozenset[str]] = {
            frozenset((str(r["source_entry_id"]), str(r["target_entry_id"])))
            for r in con.execute(
                "SELECT source_entry_id, target_entry_id FROM relations")
        }
    finally:
        con.close()
    if not rows:
        print("No records to check.")
        return 0

    records = [dict(r) for r in rows]

    stale_summary, declared_stale = [], []
    for r in records:
        summary = str(r["summary"]).lower()
        body = str(r["body"]).lower()
        status = str(r["status"])

        m = CORRECTION_RE.search(str(r["body"]))
        body_corrects = bool(m)
        summary_corrects = bool(SUMMARY_MENTION_RE.search(str(r["summary"])))
        # A record whose own title announces the correction is not hiding it.
        if SUMMARY_MENTION_RE.search(str(r["title"])):
            summary_corrects = True
        # Nor is one whose summary simply states the corrected fact without
        # calling it a correction, which is the ideal end state. Keywords
        # cannot see that; content overlap can.
        if body_corrects and not summary_corrects:
            line = str(r["body"])[m.start():m.start() + 300].splitlines()[0]
            claim = _dup_tokens(SUMMARY_MENTION_RE.sub("", line))
            if claim and len(claim & _dup_tokens(str(r["summary"]))) / len(claim) >= 0.5:
                summary_corrects = True
        if body_corrects and not summary_corrects:
            stale_summary.append(r)

        # Strip code spans first: an identifier is never a claim about the
        # record that contains it.
        plain = re.sub(r"`[^`]*`", " ", str(r["summary"]))
        says_stale = bool(DECLARED_STALE_RE.search(plain[:400]))
        kept = any(m in summary[:600] for m in KEPT_ON_PURPOSE)
        if says_stale and not kept and status not in RETIRED_STATUSES:
            declared_stale.append(r)

    # Near-duplicates over title + summary only. Bodies are long enough that
    # any two records about the same subsystem look similar; the summary is
    # where a record states what it is actually about.
    # Both sides need enough distinctive vocabulary for overlap to mean
    # anything. Below this a record is a slogan, and slogans collide.
    MIN_TOKENS = 6
    toks = [(_dup_tokens(f"{r['title']} {r['summary']}"), r) for r in records]
    pairs = []
    already_resolved = 0
    for i in range(len(toks)):
        a_tok, a = toks[i]
        if len(a_tok) < MIN_TOKENS:
            continue
        for j in range(i + 1, len(toks)):
            b_tok, b = toks[j]
            if len(b_tok) < MIN_TOKENS:
                continue
            inter = len(a_tok & b_tok)
            if not inter:
                continue
            # Jaccard, not containment. Dividing by the smaller set made every
            # short summary a near-duplicate of everything: an 8-token summary
            # needed only 6 shared words to score 75%, and one such record
            # appeared in four of eighteen reported pairs on its length alone.
            # Jaccard charges for what the two records do NOT share, so a long
            # record and a short one can no longer look identical.
            score = inter / len(a_tok | b_tok)
            if score < threshold:
                continue
            if frozenset((str(a["id"]), str(b["id"]))) in linked:
                already_resolved += 1
                continue
            pairs.append((score, a, b))
    pairs.sort(key=lambda x: -x[0])

    print(f"checked {len(records)} record(s)")
    print(f"  summaries hiding a correction : {len(stale_summary)}")
    print(f"  declared stale, status current: {len(declared_stale)}")
    print(f"  near-duplicate pairs          : {len(pairs)}")
    if already_resolved:
        print(f"  ({already_resolved} more overlap but are already linked, so not reported)")

    if stale_summary:
        print()
        print("=" * 68)
        print("THE SUMMARY DOES NOT CARRY THE CORRECTION")
        print("=" * 68)
        print("The body corrects an earlier claim; the summary still states the")
        print("old one. Search shows summaries, so the correction is invisible")
        print("to anything that does not open the record. Fix by hand: only you")
        print("know which sentence now holds.")
        print()
        for r in stale_summary[:15]:
            print(f"  {r['coll']}/{r['title'][:56]}")
            print(f"     id: {r['id']}")
            snippet = " ".join(str(r["summary"]).split())[:110]
            print(f"     summary says: {snippet}")
        if len(stale_summary) > 15:
            print(f"  ... and {len(stale_summary) - 15} more")

    if declared_stale:
        print()
        print("=" * 68)
        print("DECLARED STALE BUT STILL MARKED CURRENT")
        print("=" * 68)
        print("The record says it is superseded or outdated; its status does not.")
        print("Until the status agrees, it keeps ranking as live knowledge.")
        print()
        for r in declared_stale:
            print(f"  {r['coll']}/{r['title'][:56]}")
            print(f"     id: {r['id']}   status: {r['status']} -> superseded")
        print()
        print("  Not applied automatically. A record can announce that it is")
        print("  stale and still be the live answer. Open each one and decide;")
        print("  if it should retire, set `status: superseded` and add a")
        print("  `supersedes` relation on whatever replaced it.")

    if pairs:
        print()
        print("=" * 68)
        print("NEAR-DUPLICATE SUBJECTS")
        print("=" * 68)
        print("Two records about the same thing. Merge them, retire one with a")
        print("`supersedes` relation, or confirm they genuinely differ. Pairs")
        print("that cross collections are the usual result of merging archives.")
        print()
        for score, a, b in pairs[:20]:
            cross = "  [CROSS-COLLECTION]" if a["coll"] != b["coll"] else ""
            print(f"  {score:.0%} overlap{cross}")
            print(f"     {a['coll']}/{a['title'][:54]}")
            print(f"     {b['coll']}/{b['title'][:54]}")
        if len(pairs) > 20:
            print(f"  ... and {len(pairs) - 20} more")

    total = len(stale_summary) + len(declared_stale) + len(pairs)
    if not total:
        print()
        print("No contradictions found.")
    return 0


def _percentiles(values: list[int]) -> dict:
    if not values:
        return {}
    v = sorted(values)

    def at(q: float) -> int:
        return v[min(len(v) - 1, int(len(v) * q))]

    return {"min": v[0], "p50": at(0.5), "p90": at(0.9), "max": v[-1]}


def collect_metrics(root: Path, full: bool = False) -> dict:
    """Shape of the archive and how retrieval is going. No content, ever.

    Every value here is a count, a rate, a percentile or a score. Nothing
    identifies a record, a query, a topic, a collection or a person, because
    this is meant to be readable by someone who should not learn what the
    archive is about.
    """
    import platform

    con = ensure_db(root)
    try:
        total = con.execute("SELECT COUNT(*) c FROM entries").fetchone()["c"]
        sizes = [r["token_estimate"] for r in
                 con.execute("SELECT token_estimate FROM entries")]
        summary_lens = [len(" ".join(str(r["summary"]).split())) for r in
                        con.execute("SELECT summary FROM entries")]
        by = {}
        for field in ("entry_type", "status", "importance", "evidence",
                      "scope", "risk", "durability"):
            by[field] = {r[0]: r[1] for r in con.execute(
                f"SELECT {field}, COUNT(*) FROM entries GROUP BY {field}")}
        # Collection SIZES, never names.
        coll_sizes = sorted((r[0] for r in con.execute(
            """SELECT COUNT(e.id) FROM collections c
               LEFT JOIN entries e ON e.collection_id=c.id GROUP BY c.id""")),
            reverse=True)
        fts_rows = con.execute("SELECT COUNT(*) c FROM entry_fts").fetchone()["c"]
        relations = con.execute("SELECT COUNT(*) c FROM relations").fetchone()["c"]
        topics = con.execute("SELECT COUNT(*) c FROM topics").fetchone()["c"]
        skipped = read_meta(con, "skipped_count", "0")
    finally:
        con.close()

    m = {
        "lore_version": LORE_VERSION,
        "schema": 1,
        "captured_at": datetime.now().astimezone().replace(microsecond=0).isoformat(),
        "python": platform.python_version(),
        "platform": platform.system(),
        "archive": {
            "records": total,
            "collections": len(coll_sizes),
            "collection_sizes": coll_sizes,
            "index_rows": fts_rows,
            "index_rows_per_record": round(fts_rows / total, 1) if total else 0,
            "relations": relations,
            "topics": topics,
            "invalid_records": int(skipped or 0),
            "record_tokens": _percentiles(sizes),
            "total_tokens": sum(sizes),
            "summary_chars": _percentiles(summary_lens),
            "thin_summaries": sum(1 for n in summary_lens if n < 60),
            "distribution": by,
        },
    }

    # Retrieval: aggregates only. Query text is never read into the snapshot.
    log = root / ".lore" / "retrieval.jsonl"
    searches = shows = empty = 0
    returned: dict[str, int] = {}
    opened: set[str] = set()
    days: set[str] = set()
    if log.exists():
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            days.add(str(rec.get("at", ""))[:10])
            ids = rec.get("returned") or []
            if rec.get("action") == "search":
                searches += 1
                if not ids:
                    empty += 1
                for i in ids:
                    returned[i] = returned.get(i, 0) + 1
            elif rec.get("action") == "show":
                shows += 1
                opened.update(ids)
    m["retrieval"] = {
        "searches": searches,
        "shows": shows,
        "active_days": len(days - {""}),
        "searches_per_active_day": round(searches / max(1, len(days - {""})), 1),
        "zero_result_rate": round(empty / searches, 3) if searches else None,
        "distinct_records_returned": len(returned),
        "coverage": round(len(returned) / total, 3) if total else None,
        "open_rate": round(len(opened) / max(1, len(returned)), 3) if returned else None,
    }

    if full:
        import io
        from contextlib import redirect_stderr, redirect_stdout

        con = ensure_db(root)
        try:
            rows = [dict(r) for r in con.execute(
                "SELECT id, title FROM entries WHERE status NOT IN ('superseded','deprecated')")]
        finally:
            con.close()
        first = 0
        for r in rows:
            buf = io.StringIO()
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                try:
                    search(root, str(r["title"]), history=False, limit=1,
                           scope=None, collection=None, log=False)
                except Exception:
                    continue
            ids = re.findall(r"^   id: (\S+)", buf.getvalue(), re.M)
            if ids and ids[0] == r["id"]:
                first += 1
        m["findability"] = round(first / len(rows), 3) if rows else None

        path = _eval_path(root)
        if path.exists():
            cases = []
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    try:
                        cases.append(json.loads(line))
                    except ValueError:
                        pass
            if cases:
                res = _run_eval(root, cases)
                s = _eval_scores(res)
                m["eval"] = {"queries": len(cases),
                             **{k: round(v, 3) for k, v in s.items()}}
    return m


def _audit_export(bundle: dict) -> list[str]:
    """Paths whose string values are not provably content-free.

    Allowed: versions, ISO timestamps, the platform name, schema enum values
    (which come from Lore, not from the archive) and the disclosure note.
    Everything else in a metrics bundle should be a number.
    """
    import platform

    allowed_enums = (ENTRY_TYPES | STATUSES | IMPORTANCE | SCOPES
                     | RISKS | DURABILITY | EVIDENCE)
    offenders: list[str] = []

    def check(value, path: str) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                # Keys can be enum names (distribution buckets); anything else
                # must be a fixed field name from this file, never archive text.
                check(v, f"{path}.{k}")
        elif isinstance(value, list):
            for v in value:
                check(v, path + "[]")
        elif isinstance(value, str):
            leaf = path.rsplit(".", 1)[-1]
            if leaf in ("lore_version", "python") and re.fullmatch(r"[\d.]+", value):
                return
            if leaf in ("captured_at", "exported_at") and re.fullmatch(
                    r"[\d]{4}-[\d]{2}-[\d]{2}[T\d:+\-.]*", value):
                return
            if leaf == "platform" and value == platform.system():
                return
            if leaf == "contains" and value.startswith("counts, rates and scores only"):
                return
            if value in allowed_enums:
                return
            offenders.append(f"{path} = {value[:60]!r}")

    check(bundle, "")
    return offenders


def _metrics_path(root: Path) -> Path:
    return root / "metrics" / "daily.jsonl"


def record_daily_metrics(root: Path) -> None:
    """Append today's snapshot unless one already exists. Never raises.

    Called from every command. Daily metrics that depend on someone
    remembering to run a command are not daily metrics.
    """
    try:
        path = _metrics_path(root)
        today = datetime.now().astimezone().strftime("%Y-%m-%d")
        if path.exists():
            tail = path.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in reversed(tail[-5:]):
                if f'"captured_at": "{today}' in line:
                    return
        m = collect_metrics(root, full=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(m, ensure_ascii=False) + chr(10))
    except Exception:
        pass


def metrics(root: Path, full: bool, export: str | None) -> int:
    """Show today's metrics, or bundle the history for sharing."""
    if export:
        path = _metrics_path(root)
        history = []
        if path.exists():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip():
                    try:
                        history.append(json.loads(line))
                    except ValueError:
                        pass
        latest = collect_metrics(root, full=full)
        bundle = {
            "lore_version": LORE_VERSION,
            "metrics_schema": 1,
            "exported_at": datetime.now().astimezone().replace(microsecond=0).isoformat(),
            "contains": "counts, rates and scores only: no titles, ids, paths, "
                        "queries, topic names or collection names",
            "days": len(history),
            "history": history,
            "latest": latest,
        }
        offenders = _audit_export(bundle)
        if offenders:
            print("REFUSING TO WRITE: the bundle contains strings that are not",
                  file=sys.stderr)
            print("versions, dates, platform names or schema values. Every one of",
                  file=sys.stderr)
            print("these could carry archive content:", file=sys.stderr)
            for o in offenders[:20]:
                print(f"  {o}", file=sys.stderr)
            print("\nThis is a bug in Lore, not in your archive. Please report it.",
                  file=sys.stderr)
            return 1

        out = Path(export)
        out.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {out}  ({len(history)} daily snapshot(s))")
        print("audited: every string value is a version, date, "
              "platform name or schema value")
        print()
        print("Read it before you send it. It is plain JSON and deliberately")
        print("short: every value is a count, a rate or a score. If you find")
        print("anything in there that identifies your work, that is a bug in")
        print("Lore and worth reporting on its own.")
        return 0

    m = collect_metrics(root, full=full)
    a, r = m["archive"], m["retrieval"]
    print(f"lore {m['lore_version']}   {m['captured_at']}")
    print()
    print(f"  records            {a['records']} across {a['collections']} collection(s)")
    print(f"  index rows         {a['index_rows']} ({a['index_rows_per_record']} per record)")
    print(f"  record tokens      p50 {a['record_tokens'].get('p50')}  "
          f"p90 {a['record_tokens'].get('p90')}  max {a['record_tokens'].get('max')}")
    print(f"  summary chars      p50 {a['summary_chars'].get('p50')}  "
          f"thin {a['thin_summaries']}")
    crit = a["distribution"]["importance"].get("critical", 0)
    print(f"  critical share     {crit}/{a['records']} "
          f"({crit / a['records']:.0%})" if a["records"] else "")
    print()
    if r["searches"]:
        print(f"  searches           {r['searches']} over {r['active_days']} day(s) "
              f"({r['searches_per_active_day']}/day)")
        print(f"  found nothing      {r['zero_result_rate']:.0%}")
        print(f"  archive coverage   {r['coverage']:.0%} of records returned at least once")
        print(f"  open rate          {r['open_rate']:.0%} of returned records were opened")
    else:
        print("  searches           none yet")
    if "findability" in m:
        print()
        if m["findability"] is None:
            print("  findability        N/A (no current records to query)")
        else:
            print(f"  findability        {m['findability']:.0%}")
    if "eval" in m:
        e = m["eval"]
        print(f"  eval               r@1 {e['recall@1']:.0%}  r@3 {e['recall@3']:.0%}  "
              f"MRR {e['mrr']:.2f}  ({e['queries']} queries)")
    if not full:
        print()
        print("  (findability and eval need --full: several hundred searches)")
    return 0


def selftest() -> int:
    """Guard the ranking invariant that makes retrieval survive a real archive.

    Metadata breaks ties; it must never decide the ranking. If the positive
    metadata boosts can sum past TEXT_WEIGHT, a label alone outranks a better
    answer, and because nothing stops agents from labelling their own findings
    critical, retrieval degrades as the archive matures. That regression is
    invisible in ordinary use and invisible to a single-case test, so it is
    asserted here instead.
    """
    ok = True
    if MAX_METADATA_BOOST >= TEXT_WEIGHT:
        print(
            f"FAIL: metadata can contribute {MAX_METADATA_BOOST} against a text range "
            f"of {TEXT_WEIGHT:.0f}. A label would outvote relevance. Lower the boosts.",
            file=sys.stderr,
        )
        ok = False
    else:
        print(f"ok: metadata ceiling {MAX_METADATA_BOOST} < text weight {TEXT_WEIGHT:.0f}")

    worst = (IMPORTANCE_BOOST["critical"] + RISK_BOOST["critical"]
             + DURABILITY_BOOST["invariant"])
    share = worst / TEXT_WEIGHT
    if share > 0.5:
        print(
            f"FAIL: the critical/critical/invariant triple is worth {worst}, "
            f"{share:.0%} of the text range. Keep it under 50%.",
            file=sys.stderr,
        )
        ok = False
    else:
        print(f"ok: critical triple is {share:.0%} of the text range")

    missing_dirs = ENTRY_TYPES - set(TYPE_DIRS)
    if missing_dirs:
        print(f"FAIL: entry types with no directory mapping: {sorted(missing_dirs)}",
              file=sys.stderr)
        ok = False
    schema_types = set(re.findall(r"'([a-z_]+)'",
                       re.search(r"entry_type IN \(([^)]*)\)",
                                 schema_path().read_text(encoding="utf-8")).group(1)))
    if schema_types != ENTRY_TYPES:
        print(f"FAIL: ENTRY_TYPES and schema.sql disagree. "
              f"only in code: {sorted(ENTRY_TYPES - schema_types)}; "
              f"only in schema: {sorted(schema_types - ENTRY_TYPES)}", file=sys.stderr)
        ok = False
    else:
        print(f"ok: {len(ENTRY_TYPES)} entry types agree across code, schema and directories")

    if STATUS_BOOST["superseded"] > -TEXT_WEIGHT / 2:
        print("FAIL: the supersession penalty is too weak to retire a record.", file=sys.stderr)
        ok = False
    else:
        print("ok: retirement penalty dominates any positive boost")

    print("selftest passed." if ok else "selftest FAILED.")
    return 0 if ok else 1


def stats(root: Path) -> int:
    con = ensure_db(root)
    try:
        warn_index_state(root, con)
        total = con.execute("SELECT COUNT(*) c FROM entries").fetchone()["c"]
        tokens = con.execute("SELECT COALESCE(SUM(token_estimate),0) t FROM entries").fetchone()["t"]
        by_status = con.execute(
            "SELECT status,COUNT(*) c FROM entries GROUP BY status ORDER BY c DESC").fetchall()
        by_importance = con.execute(
            "SELECT importance,COUNT(*) c FROM entries GROUP BY importance").fetchall()
        by_collection = con.execute(
            """SELECT c.name, c.kind, COUNT(e.id) n FROM collections c
               LEFT JOIN entries e ON e.collection_id=c.id
               GROUP BY c.id ORDER BY c.name""").fetchall()

        print(f"root: {root}")
        print(f"records: {total}")
        print(f"estimated full-archive tokens: {tokens}")
        print("collections:")
        for c in by_collection:
            print(f"  - {c['name']} ({c['kind']}): {c['n']} record(s)")
        print("by status:", ", ".join(f"{r['status']}={r['c']}" for r in by_status) or "none")
        print("by importance:", ", ".join(f"{r['importance']}={r['c']}" for r in by_importance) or "none")
        skipped = read_meta(con, "skipped_count", "0")
        if skipped not in ("", "0"):
            print(f"invalid (not indexed): {skipped}")

        # Importance inflation is the failure this archive is most likely to
        # suffer and least likely to notice, because every record was written
        # by someone who thought it mattered. Measured on a 117-record
        # archive, recall@5 fell from 92% to 33% once a quarter of records
        # carried a `critical` label. The weights are capped so the collapse
        # is far gentler than that, but a label on everything still ranks
        # nothing, so say so while it is still cheap to fix.
        crit = next((r["c"] for r in by_importance if r["importance"] == "critical"), 0)
        if total >= 20:
            share = crit / total
            if share > CRITICAL_SHARE_LIMIT:
                print()
                print(
                    f"warning: {crit} of {total} records ({share:.0%}) are marked critical. "
                    f"Above about {CRITICAL_SHARE_LIMIT:.0%} the label stops carrying "
                    f"information and ranking degrades. Re-read the budget rule in "
                    f"agent/MEMORY_POLICY.md and demote the ones that are merely useful.",
                    file=sys.stderr,
                )
        return 0
    finally:
        con.close()


def validate_cmd(root: Path) -> int:
    records, errors, warnings = validate_records(root)
    for w in warnings:
        print(f"  warning: {w}")
    if errors:
        print(f"Validation failed ({len(errors)} issue(s)):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"Validation passed: {len(records)} record(s).")
    return 0


# --------------------------------------------------------------------------
# Record creation
# --------------------------------------------------------------------------

def init_archive(root: Path, json_output: bool = False) -> int:
    root = root.resolve()
    memory = root / "memory"
    if memory.exists():
        print(f"Refusing to overwrite existing archive: {memory}", file=sys.stderr)
        return 1
    memory.mkdir(parents=True)
    (memory / "README.md").write_text(
        "# Memory\n\n"
        "Canonical Lore records live below this directory. Create one with:\n\n"
        "```bash\n"
        "lore new --title \"...\" --type lesson --importance normal\n"
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
        print(f"Initialized Lore archive at {root}")
        print("Next: lore new --title \"...\" --type lesson --importance normal")
    return 0

def _records_for_mutation(root: Path) -> dict[str, dict[str, Any]] | None:
    records, errors, _ = validate_records(root)
    if errors:
        print("Refusing to modify an invalid archive. Run `lore validate`:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return None
    return {str(record["meta"]["id"]): record for record in records}


def _render_record(record: dict[str, Any], meta: dict[str, Any]) -> str:
    frontmatter = yaml.safe_dump(
        meta, sort_keys=False, allow_unicode=True, default_flow_style=False
    ).rstrip()
    return f"---\n{frontmatter}\n---\n\n{record['body'].rstrip()}\n"


def _atomic_write(path: Path, data: bytes) -> None:
    fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".updating.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


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
            f"Cannot supersede active record '{target_id}'; use `lore supersede`.",
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
            "Status 'superseded' requires `lore supersede OLD --by NEW`.",
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

-
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
        print("then run: lore rebuild")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _force_utf8_output() -> None:
    """Make stdout and stderr survive any character a record contains.

    On Windows, piping output switches stdout to the legacy ANSI code page
    (cp1252 here), and printing a character outside it raises
    UnicodeEncodeError mid-command. `lore conflicts` died halfway through its
    report on a single `→` in a record title, having already printed a
    header that made the truncated output look like a complete, short result.

    A memory tool must never be unable to display its own contents, and it
    must especially never fail in a way that resembles success. Errors are
    replaced rather than raised: a mangled glyph is a far better outcome than
    a crash that hides the rest of the report.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="lore",
        description="Lore: durable engineering memory for coding agents.")
    parser.add_argument("--root", help="workspace root (auto-detected, or set LORE_ROOT)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="initialize a new Lore archive")
    p_init.add_argument("path")
    p_init.add_argument("--json", dest="json_output", action="store_true",
                        help="emit one machine-readable JSON document")

    p_rebuild = sub.add_parser("rebuild")
    p_rebuild.add_argument("--strict", action="store_true",
                           help="exit non-zero if any record was skipped")
    sub.add_parser("validate")
    sub.add_parser("stats")
    sub.add_parser("selftest", help="assert the ranking invariants hold")
    sub.add_parser("usage", help="what retrieval actually did, from the log")
    p_met = sub.add_parser("metrics", help="archive health, safe to share")
    p_met.add_argument("--full", action="store_true",
                       help="include findability and eval (slower)")
    p_met.add_argument("--export", metavar="FILE",
                       help="write the shareable bundle to FILE")
    sub.add_parser("obsidian", help="generate Obsidian navigation notes")
    p_con = sub.add_parser("conflicts", help="find records that contradict each other")
    p_con.add_argument("--threshold", type=float, default=0.35,
                       help="near-duplicate Jaccard threshold (default 0.35)")
    p_doc = sub.add_parser("doctor", help="archive health checks, no ground truth needed")
    p_doc.add_argument("--limit", type=int, help="check only the first N records")
    p_eval = sub.add_parser("eval", help="measure retrieval against known answers")
    p_eval.add_argument("--save", metavar="NAME", help="store this run for later comparison")
    p_eval.add_argument("--against", metavar="NAME", help="compare against a stored run")

    p_search = sub.add_parser("search")
    p_search.add_argument("query")
    p_search.add_argument("--history", action="store_true")
    p_search.add_argument("--limit", type=positive_int, default=5)
    p_search.add_argument("--scope", choices=sorted(SCOPES))
    p_search.add_argument("--collection", help="restrict to one collection by name")
    p_search.add_argument("--type", dest="entry_type", choices=sorted(ENTRY_TYPES),
                          help="restrict to one record type")
    p_search.add_argument("--topic", help="restrict to one exact topic (case-insensitive)")
    p_search.add_argument("--status", choices=sorted(STATUSES),
                          help="restrict to one exact status")
    p_search.add_argument("--importance", choices=sorted(IMPORTANCE),
                          help="restrict to one exact importance level")
    p_search.add_argument("--json", dest="json_output", action="store_true",
                          help="emit one machine-readable JSON document")

    p_show = sub.add_parser("show")
    p_show.add_argument("id")
    p_show.add_argument("--json", dest="json_output", action="store_true",
                        help="emit one machine-readable JSON document")

    p_list = sub.add_parser("list", help="browse record metadata without a query")
    p_list.add_argument("--history", action="store_true",
                        help="include superseded and deprecated records")
    p_list.add_argument("--limit", type=positive_int, default=50)
    p_list.add_argument("--type", dest="entry_type", choices=sorted(ENTRY_TYPES))
    p_list.add_argument("--topic", help="restrict to one exact topic (case-insensitive)")
    p_list.add_argument("--collection", help="restrict to one collection by name")
    p_list.add_argument("--status", choices=sorted(STATUSES),
                        help="restrict to one exact status")
    p_list.add_argument("--json", dest="json_output", action="store_true",
                        help="emit one machine-readable JSON document")

    p_topics = sub.add_parser("topics", help="browse active topic vocabulary")
    p_topics.add_argument("--collection", help="restrict to one collection by name")
    p_topics.add_argument("--limit", type=positive_int, default=50)
    p_topics.add_argument("--json", dest="json_output", action="store_true",
                          help="emit one machine-readable JSON document")

    p_collections = sub.add_parser("collections", help="describe indexed collections")
    p_collections.add_argument("--json", dest="json_output", action="store_true",
                               help="emit one machine-readable JSON document")

    p_new = sub.add_parser("new", help="create a well-formed record skeleton")
    p_new.add_argument("--id", help="explicit portable record id (default: generated)")
    p_new.add_argument("--title", required=True)
    p_new.add_argument("--type", required=True, choices=sorted(ENTRY_TYPES))
    p_new.add_argument("--importance", required=True, choices=sorted(IMPORTANCE))
    p_new.add_argument("--topics", help="comma-separated topic list")
    p_new.add_argument("--status", default="current", choices=sorted(STATUSES))
    p_new.add_argument("--scope", default="subsystem", choices=sorted(SCOPES))
    p_new.add_argument("--risk", default="low", choices=sorted(RISKS))
    p_new.add_argument("--durability", default="situational", choices=sorted(DURABILITY))
    p_new.add_argument("--evidence", default="documented", choices=sorted(EVIDENCE))
    p_new.add_argument("--summary")
    p_new.add_argument("--knowledge")
    p_new.add_argument("--verification")
    p_new.add_argument("--collection", help="target collection name (default: workspace root)")
    p_new.add_argument("--json", dest="json_output", action="store_true",
                       help="emit one machine-readable JSON document")
    p_new.add_argument("--dry-run", action="store_true",
                       help="preview the exact record without writing it")

    p_relate = sub.add_parser("relate", help="add a relationship between records")
    p_relate.add_argument("source")
    p_relate.add_argument("relation_type", choices=sorted(RELATION_TYPES))
    p_relate.add_argument("target")

    p_unrelate = sub.add_parser("unrelate", help="remove a relationship between records")
    p_unrelate.add_argument("source")
    p_unrelate.add_argument("relation_type", choices=sorted(RELATION_TYPES))
    p_unrelate.add_argument("target")

    p_supersede = sub.add_parser("supersede", help="retire a record with its replacement")
    p_supersede.add_argument("old_id")
    p_supersede.add_argument("--by", dest="new_id", required=True,
                             help="id of the replacement record")

    p_status = sub.add_parser("status", help="change a record lifecycle status")
    p_status.add_argument("id")
    p_status.add_argument("new_status", choices=sorted(DIRECT_STATUSES))

    args = parser.parse_args()
    _force_utf8_output()
    if args.command == "init":
        return init_archive(Path(args.path), args.json_output)
    root = workspace_root(args.root)
    if args.command not in (None, "selftest"):
        record_daily_metrics(root)

    if args.command == "rebuild":
        return rebuild(root, strict=args.strict)
    if args.command == "validate":
        return validate_cmd(root)
    if args.command == "search":
        return search(root, args.query, args.history, args.limit, args.scope, args.collection,
                      entry_type=args.entry_type, topic=args.topic,
                      json_output=args.json_output, status=args.status,
                      importance=args.importance)
    if args.command == "show":
        return show(root, args.id, json_output=args.json_output)
    if args.command == "list":
        return list_records(root, args.history, args.limit, args.entry_type,
                            args.topic, args.collection, args.json_output, args.status)
    if args.command == "topics":
        return list_topics(root, args.limit, args.collection, args.json_output)
    if args.command == "collections":
        return list_collections(root, args.json_output)
    if args.command == "stats":
        return stats(root)
    if args.command == "selftest":
        return selftest()
    if args.command == "usage":
        return usage(root)
    if args.command == "doctor":
        return doctor(root, args.limit)
    if args.command == "metrics":
        return metrics(root, args.full, args.export)
    if args.command == "obsidian":
        return obsidian(root)
    if args.command == "conflicts":
        return conflicts(root, args.threshold)
    if args.command == "eval":
        return evaluate(root, args.save, args.against)
    if args.command == "new":
        return new_record(root, args)
    if args.command == "relate":
        return relate(root, args.source, args.relation_type, args.target)
    if args.command == "unrelate":
        return unrelate(root, args.source, args.relation_type, args.target)
    if args.command == "supersede":
        return supersede_record(root, args.old_id, args.new_id)
    if args.command == "status":
        return set_record_status(root, args.id, args.new_status)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
