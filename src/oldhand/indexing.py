"""Oldhand: indexing layer. Split out of the former single-file CLI."""

from __future__ import annotations

from . import __version__ as OLDHAND_VERSION
from datetime import datetime
from pathlib import Path
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile

from .constants import RELATION_TYPES, SECTION_MARKER
from .workspace import (
    collection_id,
    collection_name,
    db_path,
    discover_collections,
    display_path,
    schema_path,
)
from .records import record_files
from .validation import validate_records


def connect(root: Path) -> sqlite3.Connection:
    db = db_path(root)
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    return con


def token_estimate(text: str) -> int:
    # Deliberately deterministic, dependency-free approximation.
    return max(1, round(len(text) / 4))


_STRUCTURAL_HEADING = re.compile(
    r"^(context|changes|links|summary|from the summary|risks|testing|"
    r"follow.?up|rollback|verification|references|knowledge|what changed"
    r"( and why it mattered)?|background|overview)\b",
    re.I)


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
    # Fingerprint the same source snapshot that validation is about to parse.
    # If a file changes during the build, the stored value intentionally stays
    # old so ensure_db() detects the mismatch and repairs it on the next read.
    source_fingerprint = archive_fingerprint(root)
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
            ("oldhand_version", OLDHAND_VERSION),
            ("skipped_count", str(len(errors))),
            ("indexed_count", str(len(records))),
            ("fingerprint", source_fingerprint),
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
        print("Run `oldhand validate` to gate on these.", file=sys.stderr)
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
        "> Generated by `oldhand rebuild`. Do not edit manually.",
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
        'python tools/oldhand/oldhand.py search "<query>"',
        "python tools/oldhand/oldhand.py show <record-id>",
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
    built_by = read_meta(con, "oldhand_version") or read_meta(con, "lore_version")
    current = archive_fingerprint(root)
    if schema != "1" or built_by != OLDHAND_VERSION or not stored or stored != current:
        con.close()
        if stored and stored != current:
            print("note: memory Markdown changed since the last build; reindexing.",
                  file=sys.stderr)
        elif built_by and built_by != OLDHAND_VERSION:
            print(f"note: index was built by oldhand {built_by}; reindexing.",
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
    """Append one line per retrieval to .oldhand/retrieval.jsonl.

    Without this there is no way to answer the questions the migration plan
    says to measure: which records are ever returned, which returned records
    are ever opened, and how often a search finds nothing. An archive's
    characteristic failure is accumulating records nothing ever retrieves, and
    that failure is invisible unless retrieval is recorded.

    Local, derived, gitignored with the rest of `.oldhand/`, and never allowed
    to break a search: any failure here is silently ignored.
    """
    try:
        line = json.dumps({
            "at": datetime.now().astimezone().replace(microsecond=0).isoformat(),
            "action": action,
            "query": query,
            "returned": returned,
        }, ensure_ascii=False)
        path = root / ".oldhand" / "retrieval.jsonl"
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
            f"invalid. Run `oldhand validate` to see them.",
            file=sys.stderr,
        )
