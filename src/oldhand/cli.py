"""
Oldhand: durable engineering memory for coding agents.

Canonical knowledge lives in Markdown under memory/.
SQLite is derived and can be rebuilt at any time.

Design contract:
  - validate  is the strict gate: any problem is an error and exits 1.
  - rebuild   is fail-open: it indexes every valid record, reports the ones it
              skipped, and still leaves a usable index behind.
  - search    and show never die because one record is malformed.
"""

from __future__ import annotations

# The full standard-library block is kept here even where this module does not
# use every name itself. `oldhand.cli` is the public surface: callers and tests
# reach these through it, and several tests patch attributes on the modules
# themselves, which takes effect globally regardless of which layer calls them.
import argparse
import difflib
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from . import __version__ as OLDHAND_VERSION
from . import experience
from pathlib import Path
import argparse
import sys

from .constants import (
    DIRECT_STATUSES,
    DURABILITY,
    ENTRY_TYPES,
    EVIDENCE,
    IMPORTANCE,
    RELATION_TYPES,
    RISKS,
    SCOPES,
    STATUSES,
)
from .workspace import workspace_root
from .indexing import rebuild
from .search import (
    backlinks,
    doctor,
    evaluate,
    explore_context,
    list_collections,
    list_records,
    list_topics,
    obsidian,
    search,
    show,
    usage,
)
from .analysis import (
    conflicts,
    metrics,
    record_daily_metrics,
    selftest,
    stats,
    validate_cmd,
)
from .authoring import init_archive
from .harness import (
    classify_record,
    compact_records,
    curate_topic,
    distill_run,
    new_record,
    relate,
    rename_record_id,
    set_record_status,
    setup_harness,
    supersede_record,
    unrelate,
)

# Re-exported so `oldhand.cli` keeps presenting the single surface it
# presented before the split. Importers and tests refer to these names
# through this module.
from .constants import (  # noqa: F401,E402
    CRITICAL_SHARE_LIMIT,
    DIRECT_STATUSES,
    DURABILITY,
    DURABILITY_BOOST,
    ENTRY_TYPES,
    EVIDENCE,
    EVIDENCE_BOOST,
    EVIDENCE_THRESHOLD,
    FRONTMATTER_RE,
    HEADING_RE,
    IMPORTANCE,
    IMPORTANCE_BOOST,
    LORE_DIR,
    MAX_METADATA_BOOST,
    PRUNE_DIRS,
    QUERY_WORD_RE,
    RECORD_ID_RE,
    RELATION_TYPES,
    RELEVANCE_POOL,
    RETIRED_STATUSES,
    RISKS,
    RISK_BOOST,
    SCOPES,
    SCOPE_MATCH_BOOST,
    SECTION_MARKER,
    SECTION_PENALTY,
    SECTION_RE,
    SETUP_END,
    SETUP_GUIDANCE,
    SETUP_START,
    SLUG_STRIP_RE,
    STATUSES,
    STATUS_BOOST,
    TEXT_WEIGHT,
    TOPIC_BOOST_CAP,
    TOPIC_BOOST_PER_HIT,
    TYPE_DIRS,
    yaml,
)
from .workspace import (  # noqa: F401,E402
    collection_id,
    collection_name,
    db_path,
    discover_collections,
    display_path,
    schema_path,
    workspace_root,
)
from .records import (  # noqa: F401,E402
    normalize_relations,
    parse_record,
    parse_sections,
    record_files,
)
from .validation import (  # noqa: F401,E402
    validate_records,
)
from .indexing import (  # noqa: F401,E402
    _CAMEL,
    _IDENT,
    _MIN_SECTION_CHARS,
    _STRUCTURAL_HEADING,
    archive_fingerprint,
    connect,
    content_hash,
    ensure_db,
    expand_identifiers,
    generate_index,
    log_retrieval,
    read_meta,
    rebuild,
    split_sections,
    token_estimate,
    warn_index_state,
)
from .search import (  # noqa: F401,E402
    _eval_path,
    _eval_runs_dir,
    _eval_scores,
    _run_eval,
    backlinks,
    doctor,
    evaluate,
    explore_context,
    fts_query,
    list_collections,
    list_records,
    list_topics,
    obsidian,
    search,
    show,
    usage,
)
from .analysis import (  # noqa: F401,E402
    CORRECTION_RE,
    DECLARED_STALE_RE,
    KEPT_ON_PURPOSE,
    METRICS_EXPORT_KEYS,
    SUMMARY_MENTION_RE,
    _DUP_STOP,
    _MARKERS,
    _audit_export,
    _canonical_metrics_history,
    _dup_tokens,
    _is_metrics_snapshot,
    _metrics_path,
    _metrics_time,
    _percentiles,
    _reject_json_constant,
    collect_metrics,
    conflicts,
    metrics,
    record_daily_metrics,
    selftest,
    stats,
    validate_cmd,
)
from .authoring import (  # noqa: F401,E402
    init_archive,
)
from .harness import (  # noqa: F401,E402
    _atomic_write,
    _owned_setup_range,
    _publish_record_updates,
    _records_for_mutation,
    _render_record,
    _safe_setup_path,
    _setup_block,
    _setup_diff,
    _setup_target,
    classify_record,
    compact_records,
    curate_topic,
    distill_run,
    existing_ids,
    new_record,
    relate,
    rename_record_id,
    resolve_target_collection,
    set_record_status,
    setup_harness,
    slugify,
    supersede_record,
    unrelate,
)



def _force_utf8_output() -> None:
    """Make stdout and stderr survive any character a record contains.

    On Windows, piping output switches stdout to the legacy ANSI code page
    (cp1252 here), and printing a character outside it raises
    UnicodeEncodeError mid-command. `oldhand conflicts` died halfway through its
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
        prog="oldhand",
        description="Oldhand: durable engineering memory for coding agents.")
    parser.add_argument("-V", "--version", action="version",
                        version=f"%(prog)s {OLDHAND_VERSION}")
    parser.add_argument("--root", help="workspace root (auto-detected, or set LORE_ROOT)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="initialize a new Oldhand archive")
    p_init.add_argument("path")
    p_init.add_argument("--json", dest="json_output", action="store_true",
                        help="emit one machine-readable JSON document")
    p_setup = sub.add_parser("setup", help="preview a conservative harness instruction")
    p_setup.add_argument("harness", choices=("claude", "codex", "cursor", "opencode"))
    p_setup.add_argument("--apply", action="store_true",
                         help="write the displayed project-local change")
    p_setup.add_argument("--undo", action="store_true",
                         help="remove only Oldhand-owned setup content (requires --apply to write)")

    p_rebuild = sub.add_parser("rebuild")
    p_rebuild.add_argument("--strict", action="store_true",
                           help="exit non-zero if any record was skipped")
    p_validate = sub.add_parser("validate")
    p_validate.add_argument("--json", dest="json_output", action="store_true",
                            help="emit one machine-readable JSON document")
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

    p_backlinks = sub.add_parser("backlinks", help="show incoming and outgoing relations")
    p_backlinks.add_argument("id")
    p_backlinks.add_argument("--json", dest="json_output", action="store_true",
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
    p_list.add_argument("--importance", choices=sorted(IMPORTANCE),
                        help="restrict to one exact importance level")
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

    p_rename = sub.add_parser("rename", help="rename a record id and its backlinks")
    p_rename.add_argument("old_id")
    p_rename.add_argument("new_id")

    p_topic = sub.add_parser("topic", help="add or remove a record topic")
    p_topic.add_argument("id")
    topic_action = p_topic.add_mutually_exclusive_group(required=True)
    topic_action.add_argument("--add")
    topic_action.add_argument("--remove")

    p_classify = sub.add_parser("classify", help="update record classification metadata")
    p_classify.add_argument("id")
    p_classify.add_argument("--importance", choices=sorted(IMPORTANCE))
    p_classify.add_argument("--scope", choices=sorted(SCOPES))
    p_classify.add_argument("--risk", choices=sorted(RISKS))
    p_classify.add_argument("--durability", choices=sorted(DURABILITY))
    p_classify.add_argument("--evidence", choices=sorted(EVIDENCE))

    p_compact = sub.add_parser("compact", help="retire sources into a prepared target")
    p_compact.add_argument("--into", dest="target", required=True)
    p_compact.add_argument("sources", nargs="+")
    p_compact.add_argument("--dry-run", action="store_true")
    p_compact.add_argument("--json", dest="json_output", action="store_true")

    p_run_start = sub.add_parser("run-start", help="start a structured discovery run")
    p_run_start.add_argument("--id")
    p_run_start.add_argument("--task", required=True)
    p_run_start.add_argument("--evaluator", required=True)
    p_run_start.add_argument("--policy", default="manual")
    p_run_start.add_argument("--goal", choices=("maximize", "minimize"), default="maximize")
    p_run_start.add_argument("--workers", type=positive_int, default=1)
    p_run_start.add_argument("--workspace-ref")
    p_run_start.add_argument("--json", dest="json_output", action="store_true")

    p_attempt_add = sub.add_parser("attempt-add", help="add a node to a discovery run")
    p_attempt_add.add_argument("run_id")
    p_attempt_add.add_argument("--id", required=True, dest="node_id")
    p_attempt_add.add_argument("--parent", required=True)
    p_attempt_add.add_argument("--proposal", required=True)
    p_attempt_add.add_argument("--artifact-ref")
    p_attempt_add.add_argument("--policy-version")
    p_attempt_add.add_argument("--json", dest="json_output", action="store_true")

    p_attempt_eval = sub.add_parser("attempt-evaluate", help="attach an evaluation to an attempt")
    p_attempt_eval.add_argument("run_id")
    p_attempt_eval.add_argument("node_id")
    p_attempt_eval.add_argument("--score", required=True, type=float)
    correctness = p_attempt_eval.add_mutually_exclusive_group(required=True)
    correctness.add_argument("--correct", dest="correct", action="store_true")
    correctness.add_argument("--incorrect", dest="correct", action="store_false")
    p_attempt_eval.add_argument("--outcome", required=True,
                                choices=("success", "failure", "error"))
    p_attempt_eval.add_argument("--cost", type=int, default=1)
    p_attempt_eval.add_argument("--duration-ms", type=int, default=0)
    p_attempt_eval.add_argument("--diagnostics-ref")
    p_attempt_eval.add_argument("--json", dest="json_output", action="store_true")

    p_run_finish = sub.add_parser("run-finish", help="complete a fully evaluated run")
    p_run_finish.add_argument("run_id")
    p_run_finish.add_argument("--json", dest="json_output", action="store_true")

    p_run_validate = sub.add_parser("run-validate", help="validate discovery traces")
    p_run_validate.add_argument("run_id", nargs="?")
    p_run_validate.add_argument("--json", dest="json_output", action="store_true")

    p_runs = sub.add_parser("runs", help="browse discovery histories")
    p_runs.add_argument("--status", choices=("active", "completed"))
    p_runs.add_argument("--json", dest="json_output", action="store_true")

    p_run_show = sub.add_parser("run-show", help="show one discovery tree")
    p_run_show.add_argument("run_id")
    p_run_show.add_argument("--json", dest="json_output", action="store_true")

    p_replay = sub.add_parser("replay", help="replay an exploration policy offline")
    p_replay.add_argument("run_id")
    p_replay.add_argument("--policy", required=True, choices=experience.REPLAY_POLICIES)
    p_replay.add_argument("--budget", required=True, type=positive_int)
    p_replay.add_argument("--workers", type=positive_int,
                          help="parallel workers (default: run maximum)")
    p_replay.add_argument("--beta-cost", type=float, default=0.0)
    p_replay.add_argument("--beta-parallel", type=float, default=0.0)
    p_replay.add_argument("--json", dest="json_output", action="store_true")

    p_compare = sub.add_parser("policy-compare", help="compare replay policies on history")
    p_compare.add_argument("policies", nargs="+", choices=experience.REPLAY_POLICIES)
    p_compare.add_argument("--incumbent", choices=experience.REPLAY_POLICIES,
                           default="breadth")
    p_compare.add_argument("--budget", required=True, type=positive_int)
    p_compare.add_argument("--holdout", type=int, default=1)
    p_compare.add_argument("--evaluator")
    p_compare.add_argument("--goal", choices=("maximize", "minimize"))
    p_compare.add_argument("--workers", type=positive_int)
    p_compare.add_argument("--beta-cost", type=float, default=0.0)
    p_compare.add_argument("--beta-parallel", type=float, default=0.0)
    p_compare.add_argument("--json", dest="json_output", action="store_true")

    p_context = sub.add_parser(
        "explore-context", help="build a diversity-preserving context pack")
    p_context.add_argument("query")
    p_context.add_argument("--workers", required=True, type=positive_int)
    p_context.add_argument("--history-branches", type=int, default=1)
    p_context.add_argument("--per-branch", type=positive_int, default=5)
    p_context.add_argument("--json", dest="json_output", action="store_true")

    p_distill = sub.add_parser(
        "run-distill", help="distill one reviewed attempt into durable memory")
    p_distill.add_argument("run_id")
    p_distill.add_argument("node_id")
    p_distill.add_argument("--id")
    p_distill.add_argument("--title", required=True)
    p_distill.add_argument("--type", dest="entry_type", required=True,
                           choices=sorted(ENTRY_TYPES))
    p_distill.add_argument("--importance", required=True, choices=sorted(IMPORTANCE))
    p_distill.add_argument("--topics", required=True)
    p_distill.add_argument("--summary")
    p_distill.add_argument("--scope", default="subsystem", choices=sorted(SCOPES))
    p_distill.add_argument("--risk", default="low", choices=sorted(RISKS))
    p_distill.add_argument("--durability", default="situational",
                           choices=sorted(DURABILITY))
    p_distill.add_argument("--collection")
    p_distill.add_argument("--dry-run", action="store_true")
    p_distill.add_argument("--json", dest="json_output", action="store_true")

    args = parser.parse_args()
    _force_utf8_output()
    if args.command == "init":
        return init_archive(Path(args.path), args.json_output)
    root = workspace_root(args.root)
    # `setup` must be a true preview by default; recording daily metrics would
    # make its dry-run mutate the archive.
    if args.command in (None, "selftest", "setup"):
        return _dispatch(args, root)
    # Record once the command has returned - including a nonzero return or an
    # exception - so today's upsert observes its final archive and log state.
    # try/finally does that deterministically on every platform; atexit did
    # not run reliably everywhere and failed silently when it did not.
    try:
        return _dispatch(args, root)
    finally:
        record_daily_metrics(root)


def _dispatch(args, root: Path) -> int:
    if args.command == "rebuild":
        return rebuild(root, strict=args.strict)
    if args.command == "setup":
        return setup_harness(root, args.harness, args.apply, args.undo)
    if args.command == "validate":
        return validate_cmd(root, args.json_output)
    if args.command == "search":
        return search(root, args.query, args.history, args.limit, args.scope, args.collection,
                      entry_type=args.entry_type, topic=args.topic,
                      json_output=args.json_output, status=args.status,
                      importance=args.importance)
    if args.command == "show":
        return show(root, args.id, json_output=args.json_output)
    if args.command == "backlinks":
        return backlinks(root, args.id, args.json_output)
    if args.command == "list":
        return list_records(root, args.history, args.limit, args.entry_type,
                            args.topic, args.collection, args.json_output, args.status,
                            args.importance)
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
    if args.command == "rename":
        return rename_record_id(root, args.old_id, args.new_id)
    if args.command == "topic":
        return curate_topic(root, args.id, args.add, args.remove)
    if args.command == "classify":
        return classify_record(root, args.id, importance=args.importance,
                               scope=args.scope, risk=args.risk,
                               durability=args.durability, evidence=args.evidence)
    if args.command == "compact":
        return compact_records(root, args.target, args.sources,
                               args.dry_run, args.json_output)
    if args.command == "run-start":
        return experience.start_run(
            root, args.task, args.evaluator, args.policy, args.goal, args.workers,
            args.id, args.workspace_ref, args.json_output)
    if args.command == "attempt-add":
        return experience.add_attempt(
            root, args.run_id, args.node_id, args.parent, args.proposal,
            args.artifact_ref, args.policy_version, args.json_output)
    if args.command == "attempt-evaluate":
        return experience.evaluate_attempt(
            root, args.run_id, args.node_id, args.score, args.correct, args.outcome,
            args.cost, args.duration_ms, args.diagnostics_ref, args.json_output)
    if args.command == "run-finish":
        return experience.finish_run(root, args.run_id, args.json_output)
    if args.command == "run-validate":
        return experience.validate_runs_cmd(root, args.run_id, args.json_output)
    if args.command == "runs":
        return experience.list_runs(root, args.status, args.json_output)
    if args.command == "run-show":
        return experience.show_run(root, args.run_id, args.json_output)
    if args.command == "replay":
        return experience.replay_cmd(
            root, args.run_id, args.policy, args.budget, args.workers,
            args.beta_cost, args.beta_parallel, args.json_output)
    if args.command == "policy-compare":
        return experience.compare_policies(
            root, args.policies, args.incumbent, args.budget, args.holdout,
            args.evaluator, args.workers, args.beta_cost, args.beta_parallel,
            args.json_output, args.goal)
    if args.command == "explore-context":
        return explore_context(root, args.query, args.workers,
                               args.history_branches, args.per_branch,
                               args.json_output)
    if args.command == "run-distill":
        return distill_run(root, args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
