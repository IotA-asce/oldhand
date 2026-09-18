"""Oldhand: search layer. Split out of the former single-file CLI."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import json
import re
import sys

from .constants import (
    DURABILITY_BOOST,
    EVIDENCE_BOOST,
    EVIDENCE_THRESHOLD,
    IMPORTANCE_BOOST,
    QUERY_WORD_RE,
    RELEVANCE_POOL,
    RETIRED_STATUSES,
    RISK_BOOST,
    SCOPE_MATCH_BOOST,
    SECTION_MARKER,
    SECTION_PENALTY,
    STATUS_BOOST,
    TEXT_WEIGHT,
    TOPIC_BOOST_CAP,
    TOPIC_BOOST_PER_HIT,
)
from .workspace import display_path
from .indexing import ensure_db, log_retrieval, warn_index_state


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
    bury genuine traffic under tooling and make `oldhand usage` measure itself.
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


def explore_context(root: Path, query: str, workers: int,
                    history_branches: int = 1, per_branch: int = 5,
                    json_output: bool = False) -> int:
    """Build parallel context without forcing directional history on every branch."""
    if history_branches < 0 or history_branches > workers:
        print("history branches must be between zero and workers", file=sys.stderr)
        return 2
    from contextlib import redirect_stdout
    from io import StringIO

    buffer = StringIO()
    with redirect_stdout(buffer):
        rc = search(root, query, history=False,
                    limit=max(50, workers * per_branch), scope=None,
                    collection=None, log=False, json_output=True)
    if rc != 0:
        return rc
    payload = json.loads(buffer.getvalue())
    results = payload["results"]
    guardrails = [item for item in results if (
        (item["type"] == "constraint" and item["importance"] == "critical")
        or (item["risk"] == "critical" and item["durability"] == "invariant")
    )]
    guardrail_ids = {item["id"] for item in guardrails}
    directional = [item for item in results if item["id"] not in guardrail_ids]
    branches = []
    for index in range(workers):
        guided = index < history_branches
        branches.append({
            "worker": index + 1,
            "mode": "history-guided" if guided else "independent",
            "shared_guardrail_ids": [item["id"] for item in guardrails],
            "records": directional[:per_branch] if guided else [],
        })
    context = {
        "query": query, "workers": workers,
        "history_branches": history_branches,
        "shared_guardrails": guardrails,
        "branches": branches,
        "principle": "Guardrails are shared; directional history is isolated to selected branches.",
    }
    if json_output:
        print(json.dumps(context, ensure_ascii=False, indent=2))
    else:
        print(f"Exploration context for {workers} worker(s)")
        print("Shared guardrails: " +
              (", ".join(item["id"] for item in guardrails) or "none"))
        for branch in branches:
            ids = ", ".join(item["id"] for item in branch["records"]) or "none"
            print(f"- worker {branch['worker']} [{branch['mode']}]: {ids}")
    return 0


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
                 json_output: bool = False, status: str | None = None,
                 importance: str | None = None) -> int:
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
        if importance:
            clauses.append("e.importance = ?")
            params.append(importance)
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
                    "importance": importance,
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


def backlinks(root: Path, record_id: str, json_output: bool = False) -> int:
    """Show every indexed edge touching a record."""
    con = ensure_db(root)
    try:
        record = con.execute(
            "SELECT id, title FROM entries WHERE id=?", (record_id,)
        ).fetchone()
        if record is None:
            print(f"Unknown record id: {record_id}", file=sys.stderr)
            return 1
        incoming = [dict(row) for row in con.execute(
            """SELECT r.relation_type AS type, e.id, e.title, e.status
               FROM relations r JOIN entries e ON e.id=r.source_entry_id
               WHERE r.target_entry_id=? ORDER BY r.relation_type, e.id""",
            (record_id,),
        ).fetchall()]
        outgoing = [dict(row) for row in con.execute(
            """SELECT r.relation_type AS type, e.id, e.title, e.status
               FROM relations r JOIN entries e ON e.id=r.target_entry_id
               WHERE r.source_entry_id=? ORDER BY r.relation_type, e.id""",
            (record_id,),
        ).fetchall()]
        payload = {
            "id": record_id, "title": record["title"],
            "incoming": incoming, "outgoing": outgoing,
        }
        if json_output:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"{record['title']} ({record_id})")
            for label, edges in (("Incoming", incoming), ("Outgoing", outgoing)):
                print(f"\n{label} ({len(edges)}):")
                if not edges:
                    print("  none")
                for edge in edges:
                    print(f"  {edge['type']}: {edge['id']} — {edge['title']} [{edge['status']}]")
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
    """Report what retrieval actually did, from .oldhand/retrieval.jsonl.

    The question that decides whether an archive is earning its keep is not
    how many records it holds, it is how many of them anything has ever
    retrieved. A record nothing returns costs tokens to write, adds noise to
    every ranking afterwards, and has never once been useful. Without this
    command the log is write-only and that question stays unanswerable.
    """
    log = root / ".oldhand" / "retrieval.jsonl"
    if not log.exists():
        print("No retrieval log yet. It is written by `oldhand search` and `oldhand show`.")
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
    """Saved eval runs live beside the queries, not under .oldhand/.

    A baseline is a measurement record, not derived state. Keeping it in
    .oldhand/ meant any rebuild or reset destroyed the thing you were measuring
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
        print(f"\nSaved as '{save}'. Compare later with: oldhand eval --against {save}")

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

    home = ["# Oldhand", "",
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
             "Generated by `oldhand obsidian`. Edits here are overwritten.",
             "Canonical records live under each collection's `memory/`."]
    (root / "HOME.md").write_text("\n".join(home), encoding="utf-8", newline="\n")

    print(f"wrote HOME.md and {len(topics)} topic hub(s) in {display_path(root, hub_dir)}")
    print()
    print("Open the archive as a vault: Obsidian > Open folder as vault >")
    print(f"  {root}")
    print("Then open HOME.md. Graph view will show topic hubs as cluster centres.")
    print()
    print("Generated notes sit outside memory/, so oldhand never indexes them.")
    return 0
