"""Oldhand: analysis layer. Split out of the former single-file CLI."""

from __future__ import annotations

from . import __version__ as OLDHAND_VERSION
from datetime import datetime
from pathlib import Path
from typing import Any
import json
import math
import os
import re
import sys
import traceback

from .constants import (
    CRITICAL_SHARE_LIMIT,
    DURABILITY,
    DURABILITY_BOOST,
    ENTRY_TYPES,
    EVIDENCE,
    IMPORTANCE,
    IMPORTANCE_BOOST,
    MAX_METADATA_BOOST,
    RETIRED_STATUSES,
    RISKS,
    RISK_BOOST,
    SCOPES,
    STATUSES,
    STATUS_BOOST,
    TEXT_WEIGHT,
    TYPE_DIRS,
)
from .workspace import _atomic_write, schema_path
from .validation import validate_records
from .indexing import ensure_db, read_meta, warn_index_state
from .search import _eval_path, _eval_scores, _run_eval, search


_MARKERS = (r"CORRECTED|CORRECTION|CORRECTS|RETRACTION|RETRACTED|"
            r"SUPERSEDED|SUPERSEDES|OUTDATED|NO LONGER TRUE|OBSOLETE|"
            r"UPDATED|UPDATE")


CORRECTION_RE = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]*)?\**[ \t]*(?:" + _MARKERS + r")\b"
    r"[ \t]*(?:\*{0,2}[ \t]*)(?::|\d{4}-\d{2}-\d{2}|\bon\b|\bby\b)",
    re.M)


SUMMARY_MENTION_RE = re.compile(r"(?:" + _MARKERS + r")\b", re.I)


DECLARED_STALE_RE = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]*)?\**[ \t]*"
    r"(?:SUPERSEDED|OUTDATED|OBSOLETE|DEPRECATED|DO NOT USE|NO LONGER APPLIES)"
    r"\b[ \t]*\**[ \t]*(?::|\d{4}-\d{2}-\d{2}|\bby\b|\bin favour\b|$)",
    re.M)


KEPT_ON_PURPOSE = ("kept for", "keeping for", "for the history", "for history",
                   "still true", "still applies", "still valid", "still the",
                   "kept because", "retained for", "instructive")


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
        record_ids = {str(r["id"]) for r in con.execute("SELECT id FROM entries")}
        total = len(record_ids)
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
        "oldhand_version": OLDHAND_VERSION,
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
    log = root / ".oldhand" / "retrieval.jsonl"
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
            if not isinstance(rec, dict):
                continue
            action = rec.get("action")
            at = rec.get("at")
            ids = rec.get("returned")
            if (action not in ("search", "show")
                    or not isinstance(at, str)
                    or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", at[:10])
                    or not isinstance(ids, list)
                    or any(not isinstance(item, str) for item in ids)):
                continue
            days.add(at[:10])
            if action == "search":
                searches += 1
                if not ids:
                    empty += 1
                for i in ids:
                    if i in record_ids:
                        returned[i] = returned.get(i, 0) + 1
            else:
                shows += 1
                opened.update(i for i in ids if i in record_ids)
    m["retrieval"] = {
        "searches": searches,
        "shows": shows,
        "active_days": len(days - {""}),
        "searches_per_active_day": round(searches / max(1, len(days - {""})), 1),
        "zero_result_rate": round(empty / searches, 3) if searches else None,
        "distinct_records_returned": len(returned),
        "coverage": round(len(returned) / total, 3) if total else None,
        "open_rate": round(len(opened & returned.keys()) / len(returned), 3)
        if returned else None,
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


METRICS_EXPORT_KEYS = {
    "oldhand_version", "lore_version", "metrics_schema", "exported_at",
    "contains", "days",
    "history", "latest", "schema", "captured_at", "python", "platform",
    "archive", "retrieval", "findability", "eval", "records", "collections",
    "collection_sizes", "index_rows", "index_rows_per_record", "relations",
    "topics", "invalid_records", "record_tokens", "total_tokens",
    "summary_chars", "thin_summaries", "distribution", "entry_type", "status",
    "importance", "evidence", "scope", "risk", "durability", "searches",
    "shows", "active_days", "searches_per_active_day", "zero_result_rate",
    "distinct_records_returned", "coverage", "open_rate", "min", "p50", "p90",
    "max", "queries", "recall@1", "recall@3", "recall@5", "mrr",
} | ENTRY_TYPES | STATUSES | IMPORTANCE | SCOPES | RISKS | DURABILITY | EVIDENCE


def _audit_export(bundle: dict) -> list[str]:
    """Paths whose keys or string values are not provably content-free.

    Allowed: versions, ISO timestamps, the platform name, schema enum values
    (which come from Oldhand, not from the archive) and the disclosure note.
    Everything else in a metrics bundle should be a number.
    """
    import platform

    allowed_enums = (ENTRY_TYPES | STATUSES | IMPORTANCE | SCOPES
                     | RISKS | DURABILITY | EVIDENCE)
    offenders: list[str] = []

    def check(value, path: str) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                if not isinstance(k, str) or k not in METRICS_EXPORT_KEYS:
                    offenders.append(f"{path}.{k} = <unexpected field>")
                    continue
                check(v, f"{path}.{k}")
        elif isinstance(value, list):
            for v in value:
                check(v, path + "[]")
        elif isinstance(value, float) and not math.isfinite(value):
            offenders.append(f"{path} = <non-finite number>")
        elif isinstance(value, str):
            leaf = path.rsplit(".", 1)[-1]
            if leaf in ("oldhand_version", "lore_version", "python") and re.fullmatch(
                    r"\d+(?:\.\d+)*(?:(?:a|b|rc)\d+)?(?:\.post\d+)?(?:\.dev\d+)?", value):
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


def _is_metrics_snapshot(value: Any) -> bool:
    """Return whether a value has the complete schema-1 snapshot envelope."""
    if not isinstance(value, dict) or value.get("schema") != 1:
        return False
    # `lore_version` is the pre-rename spelling. Accept it so metrics history
    # recorded before the rename is not retroactively treated as malformed.
    if not isinstance(value.get("oldhand_version") or value.get("lore_version"), str):
        return False
    if not all(isinstance(value.get(key), str)
               for key in ("captured_at", "python", "platform")):
        return False
    try:
        _metrics_time(value["captured_at"])
    except (TypeError, ValueError):
        return False
    archive = value.get("archive")
    retrieval = value.get("retrieval")
    if not isinstance(archive, dict) or not isinstance(retrieval, dict):
        return False
    archive_keys = {
        "records", "collections", "collection_sizes", "index_rows",
        "index_rows_per_record", "relations", "topics", "invalid_records",
        "record_tokens", "total_tokens", "summary_chars", "thin_summaries",
        "distribution",
    }
    retrieval_keys = {
        "searches", "shows", "active_days", "searches_per_active_day",
        "zero_result_rate", "distinct_records_returned", "coverage", "open_rate",
    }
    def finite(item: Any) -> bool:
        if isinstance(item, float):
            return math.isfinite(item)
        if isinstance(item, dict):
            return all(finite(child) for child in item.values())
        if isinstance(item, list):
            return all(finite(child) for child in item)
        return True

    return (archive_keys <= set(archive) and retrieval_keys <= set(retrieval)
            and finite(value))


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _metrics_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("metrics timestamp must be a string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None or "T" not in value:
        raise ValueError("metrics timestamp must include time and UTC offset")
    return parsed


def _canonical_metrics_history(rows: list[dict]) -> tuple[list[dict], int]:
    latest: dict[str, tuple[datetime, dict]] = {}
    duplicates = 0
    for row in rows:
        instant = _metrics_time(row["captured_at"])
        day = row["captured_at"][:10]
        current = latest.get(day)
        if current is not None:
            duplicates += 1
        if current is None or instant > current[0]:
            latest[day] = (instant, row)
    return [latest[day][1] for day in sorted(latest)], duplicates


def record_daily_metrics(root: Path) -> None:
    """Atomically upsert today's snapshot. Never raises.

    Registered after root resolution and run at process exit, so the snapshot
    includes the command that just completed. Replacing today's row retains a
    single daily sample while keeping same-day activity current.
    """
    try:
        path = _metrics_path(root)
        today = datetime.now().astimezone().strftime("%Y-%m-%d")
        invalid_rows: list[str] = []
        snapshots: list[dict] = []
        if path.exists():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    existing = json.loads(line, parse_constant=_reject_json_constant)
                except ValueError:
                    invalid_rows.append(line)
                    continue
                if not _is_metrics_snapshot(existing):
                    invalid_rows.append(line)
                    continue
                captured = existing.get("captured_at")
                if not isinstance(captured, str) or captured[:10] != today:
                    snapshots.append(existing)
        m = collect_metrics(root, full=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        snapshots.append(m)
        snapshots, _ = _canonical_metrics_history(snapshots)
        rows = invalid_rows + [json.dumps(
            snapshot, ensure_ascii=False, allow_nan=False) for snapshot in snapshots]
        _atomic_write(path, ("\n".join(rows) + "\n").encode("utf-8"))
    except Exception:
        # Metrics must never break the command the user actually asked for,
        # but silence here once hid a real platform failure for an entire
        # release. LORE_DEBUG makes it visible without changing behaviour.
        if os.environ.get("LORE_DEBUG"):
            traceback.print_exc()


def metrics(root: Path, full: bool, export: str | None) -> int:
    """Show today's metrics, or bundle the history for sharing."""
    if export:
        path = _metrics_path(root)
        out = Path(export)
        try:
            same_source = out.resolve(strict=False) == path.resolve(strict=False)
            if out.exists() and path.exists():
                same_source = same_source or os.path.samefile(out, path)
        except OSError as error:
            print(f"REFUSING TO WRITE: cannot verify export path: {error}",
                  file=sys.stderr)
            return 1
        if same_source:
            print("REFUSING TO WRITE: export destination is the daily metrics history.",
                  file=sys.stderr)
            return 1
        history = []
        invalid_history = 0
        if path.exists():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip():
                    try:
                        candidate = json.loads(
                            line, parse_constant=_reject_json_constant)
                    except ValueError:
                        invalid_history += 1
                        continue
                    if _is_metrics_snapshot(candidate):
                        history.append(candidate)
                    else:
                        invalid_history += 1
        if invalid_history:
            print(f"warning: ignored {invalid_history} invalid metrics history row(s)",
                  file=sys.stderr)
        history, duplicate_days = _canonical_metrics_history(history)
        if duplicate_days:
            print(f"warning: collapsed {duplicate_days} duplicate metrics day row(s)",
                  file=sys.stderr)
        latest = collect_metrics(root, full=full)
        bundle = {
            "oldhand_version": OLDHAND_VERSION,
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
            print("\nThis is a bug in Oldhand, not in your archive. Please report it.",
                  file=sys.stderr)
            return 1

        encoded = json.dumps(
            bundle, indent=2, ensure_ascii=False, allow_nan=False).encode("utf-8")
        try:
            _atomic_write(out, encoded)
        except OSError as error:
            print(f"Cannot write metrics export {out}: {error}", file=sys.stderr)
            return 1
        print(f"wrote {out}  ({len(history)} daily snapshot(s))")
        print("audited: every string value is a version, date, "
              "platform name or schema value")
        print()
        print("Read it before you send it. It is plain JSON and deliberately")
        print("short: every value is a count, a rate or a score. If you find")
        print("anything in there that identifies your work, that is a bug in")
        print("Oldhand and worth reporting on its own.")
        return 0

    m = collect_metrics(root, full=full)
    a, r = m["archive"], m["retrieval"]
    print(f"oldhand {m['oldhand_version']}   {m['captured_at']}")
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


def validate_cmd(root: Path, json_output: bool = False) -> int:
    records, errors, warnings = validate_records(root)
    if json_output:
        print(json.dumps({
            "valid": not errors, "record_count": len(records),
            "error_count": len(errors), "warning_count": len(warnings),
            "errors": errors, "warnings": warnings,
        }, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    for w in warnings:
        print(f"  warning: {w}")
    if errors:
        print(f"Validation failed ({len(errors)} issue(s)):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"Validation passed: {len(records)} record(s).")
    return 0
