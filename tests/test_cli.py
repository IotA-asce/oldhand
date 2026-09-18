import argparse
import ast
import contextlib
import io
import json
import os
from pathlib import Path, PureWindowsPath
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import yaml


from oldhand import cli as oldhand
# `rebuild` resolves validate_records, generate_index and itself through
# the indexing module's own globals, so these must be patched where they
# are looked up rather than on the re-exporting cli surface.
from oldhand import indexing

SOURCE = Path(oldhand.__file__).resolve()


class LoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.output = io.StringIO()
        self.errors = io.StringIO()
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(contextlib.redirect_stdout(self.output))
        stack.enter_context(contextlib.redirect_stderr(self.errors))

    def record(self, name="record", **changes):
        meta = dict(schema_version=1, id=name, type="lesson", status="current",
                    importance="normal", scope="repository", risk="low",
                    durability="long_lived", evidence="verified", topics=["testing"],
                    created_at="2026-09-17T00:00:00+00:00",
                    updated_at="2026-09-17T00:00:00+00:00", relations={})
        meta.update(changes)
        path = self.root / "memory" / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("---\n" + yaml.safe_dump(meta) + "---\n\n# " + name +
                        "\n\n## Summary\n\nA useful testing finding.\n\n## Knowledge\n\nKnown facts.\n",
                        encoding="utf-8")
        return path

    def test_python_310_syntax(self):
        ast.parse(SOURCE.read_text(encoding="utf-8"), feature_version=(3, 10))

    def test_schema_versions_fail_open(self):
        self.record("valid")
        for index, value in enumerate(["v1", "1", 1.5, True, [], {}, 2]):
            self.record(f"invalid{index}", schema_version=value)
        valid, errors, _ = oldhand.validate_records(self.root)
        self.assertEqual([r["meta"]["id"] for r in valid], ["valid"])
        self.assertEqual(len(errors), 7)
        self.assertTrue(all("schema_version" in error for error in errors))
        self.assertEqual(oldhand.rebuild(self.root, quiet=True), 0)
        with contextlib.closing(oldhand.connect(self.root)) as con:
            self.assertEqual(con.execute("SELECT count(*) FROM entries").fetchone()[0], 1)

    def test_validate_json_reports_success_and_failure(self):
        self.record("valid")
        self.assertEqual(oldhand.validate_cmd(self.root, json_output=True), 0)
        payload = json.loads(self.output.getvalue())
        self.assertEqual((payload["valid"], payload["record_count"]), (True, 1))
        self.output.seek(0)
        self.output.truncate()
        self.record("bad", schema_version="v1")
        self.assertEqual(oldhand.validate_cmd(self.root, json_output=True), 1)
        payload = json.loads(self.output.getvalue())
        self.assertFalse(payload["valid"])
        self.assertEqual(payload["error_count"], 1)

    def test_malformed_relations_rejected(self):
        self.record("valid")
        for index, relations in enumerate([123, [], "target", {"supersedes": 123},
                                            {"unknown": None}, {"related_to": [None]},
                                            {"related_to": [""]}]):
            self.record(f"invalid{index}", relations=relations)
        valid, errors, _ = oldhand.validate_records(self.root)
        self.assertEqual([r["meta"]["id"] for r in valid], ["valid"])
        self.assertEqual(len(errors), 7)
        self.assertTrue(all("relation" in error for error in errors))

    def test_duplicate_ids_reject_all_ambiguous_records(self):
        self.record("a", id="shared")
        self.record("b", id="shared")
        self.record("c", id="shared")
        self.record("valid")
        valid, errors, _ = oldhand.validate_records(self.root)
        self.assertEqual([r["meta"]["id"] for r in valid], ["valid"])
        self.assertTrue(all(any(f"{name}.md:" in error for error in errors)
                            for name in ("a", "b", "c")))

    def test_fingerprint_detects_same_size_edit_with_unchanged_mtime(self):
        path = self.record("a")
        os.utime(path, (1_000_000, 1_000_000))
        self.assertEqual(oldhand.rebuild(self.root, quiet=True), 0)
        before = oldhand.archive_fingerprint(self.root)
        stat = path.stat()
        path.write_text(path.read_text(encoding="utf-8").replace("Known facts.",
                                                                 "Other facts."), encoding="utf-8")
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.assertEqual(path.stat().st_size, stat.st_size)
        self.assertEqual(path.stat().st_mtime_ns, stat.st_mtime_ns)
        self.assertNotEqual(before, oldhand.archive_fingerprint(self.root))
        with contextlib.closing(oldhand.ensure_db(self.root)) as con:
            body = con.execute("SELECT body FROM entries WHERE id='a'").fetchone()[0]
            self.assertIn("Other facts.", body)
            self.assertNotIn("Known facts.", body)

    def test_fingerprint_detects_rename_without_content_or_mtime_change(self):
        path = self.record("a")
        self.assertEqual(oldhand.rebuild(self.root, quiet=True), 0)
        before = oldhand.archive_fingerprint(self.root)
        content = path.read_bytes()
        stat = path.stat()
        renamed = path.rename(path.with_name("b.md"))
        self.assertEqual(renamed.read_bytes(), content)
        self.assertEqual(renamed.stat().st_mtime_ns, stat.st_mtime_ns)
        self.assertNotEqual(before, oldhand.archive_fingerprint(self.root))
        with contextlib.closing(oldhand.ensure_db(self.root)) as con:
            self.assertEqual(con.execute("SELECT path FROM entries WHERE id='a'").fetchone()[0],
                             "memory/b.md")

    def test_edit_during_rebuild_cannot_bless_stale_content(self):
        path = self.record("a")
        original_validate = oldhand.validate_records

        def edit_after_parse(root):
            result = original_validate(root)
            path.write_text(path.read_text(encoding="utf-8").replace(
                "Known facts.", "Other facts."), encoding="utf-8")
            return result

        with mock.patch.object(indexing, "validate_records", side_effect=edit_after_parse):
            self.assertEqual(oldhand.rebuild(self.root, quiet=True), 0)
        with contextlib.closing(oldhand.connect(self.root)) as con:
            self.assertIn("Known facts.", con.execute(
                "SELECT body FROM entries WHERE id='a'").fetchone()[0])
        with contextlib.closing(oldhand.ensure_db(self.root)) as con:
            body = con.execute("SELECT body FROM entries WHERE id='a'").fetchone()[0]
            self.assertIn("Other facts.", body)
            self.assertEqual(oldhand.read_meta(con, "fingerprint"),
                             oldhand.archive_fingerprint(self.root))

    def test_current_index_is_not_rebuilt(self):
        self.record("a")
        self.assertEqual(oldhand.rebuild(self.root, quiet=True), 0)
        with mock.patch.object(indexing, "rebuild", wraps=indexing.rebuild) as rebuild:
            self.repair_cycle()
        rebuild.assert_not_called()

    def test_old_index_version_is_rebuilt_with_unchanged_markdown(self):
        self.record("a")
        self.assertEqual(oldhand.rebuild(self.root, quiet=True), 0)
        fingerprint = oldhand.archive_fingerprint(self.root)
        for key, value in (("oldhand_version", "0.0.0"), ("schema", "0")):
            with self.subTest(key=key):
                with contextlib.closing(oldhand.connect(self.root)) as con:
                    con.execute("UPDATE index_meta SET value=? WHERE key=?", (value, key))
                    con.execute("UPDATE entries SET title='stale'")
                    con.commit()
                with mock.patch.object(indexing, "rebuild", wraps=indexing.rebuild) as rebuild:
                    self.repair_cycle()
                rebuild.assert_called_once_with(self.root, strict=False, quiet=True)
                self.assertEqual(oldhand.archive_fingerprint(self.root), fingerprint)
                with contextlib.closing(oldhand.connect(self.root)) as con:
                    self.assertEqual(oldhand.read_meta(con, key), oldhand.OLDHAND_VERSION if key == "oldhand_version" else "1")
                    self.assertEqual(con.execute("SELECT title FROM entries").fetchone()[0], "a")

    def test_empty_or_legacy_index_is_repaired(self):
        self.record("a")
        oldhand.rebuild(self.root, quiet=True)
        db = oldhand.db_path(self.root)
        with contextlib.closing(sqlite3.connect(db)) as raw:
            raw.executescript("DROP TABLE index_meta;")
            raw.commit()
        self.repair_cycle()
        for missing in ("fingerprint", "schema", "oldhand_version"):
            with contextlib.closing(sqlite3.connect(db)) as raw:
                raw.execute("DELETE FROM index_meta WHERE key=?", (missing,))
                raw.commit()
            self.repair_cycle()
        with contextlib.closing(sqlite3.connect(db)) as raw:
            raw.executescript("DROP TABLE entry_fts; DROP TABLE index_meta; DROP TABLE entries;")
            raw.commit()
        self.repair_cycle()

    def repair_cycle(self):
        with contextlib.closing(oldhand.ensure_db(self.root)) as con:
            self.assertEqual(con.execute("SELECT id FROM entries").fetchall()[0][0], "a")
            self.assertEqual(con.execute("SELECT count(*) FROM entries").fetchone()[0], 1)
            self.assertEqual(oldhand.read_meta(con, "schema"), "1")
            self.assertEqual(oldhand.read_meta(con, "oldhand_version"), oldhand.OLDHAND_VERSION)
            self.assertEqual(oldhand.read_meta(con, "fingerprint"),
                             oldhand.archive_fingerprint(self.root))

    def test_failed_rebuild_leaves_previous_index(self):
        self.record("a")
        oldhand.rebuild(self.root, quiet=True)
        db = oldhand.db_path(self.root)
        self.record("b")
        with mock.patch.object(indexing, "generate_index",
                               side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                oldhand.rebuild(self.root, quiet=True)
        with contextlib.closing(sqlite3.connect(db)) as raw:
            self.assertEqual(raw.execute("SELECT count(*) FROM entries").fetchone()[0], 1)
        self.assertEqual(list(db.parent.glob("*.building*")), [])
        with contextlib.closing(oldhand.ensure_db(self.root)) as con:
            self.assertEqual(con.execute("SELECT count(*) FROM entries").fetchone()[0], 2)

    def test_overlapping_rebuilds_use_distinct_staging_files(self):
        self.record("a")
        self.assertEqual(oldhand.rebuild(self.root, quiet=True), 0)
        db = oldhand.db_path(self.root)
        real_rebuild = oldhand.rebuild
        real_mkstemp = oldhand.tempfile.mkstemp
        staging = []

        def overlap(*args, **kwargs):
            fd, name = real_mkstemp(*args, **kwargs)
            staging.append(Path(name))
            if len(staging) == 1:
                self.assertEqual(real_rebuild(self.root, quiet=True), 0)
            return fd, name

        with mock.patch.object(oldhand.tempfile, "mkstemp", side_effect=overlap):
            self.assertEqual(oldhand.rebuild(self.root, quiet=True), 0)
        self.assertEqual(len(staging), 2)
        self.assertNotEqual(staging[0], staging[1])
        self.assertTrue(db.exists())
        self.assertEqual(list(db.parent.glob("*.building*")), [])
        self.repair_cycle()

    def test_connection_failure_cleans_staging(self):
        self.record("a")
        self.assertEqual(oldhand.rebuild(self.root, quiet=True), 0)
        db = oldhand.db_path(self.root)
        before = db.read_bytes()
        with mock.patch.object(oldhand.sqlite3, "connect", side_effect=sqlite3.OperationalError("boom")):
            with self.assertRaisesRegex(sqlite3.OperationalError, "boom"):
                oldhand.rebuild(self.root, quiet=True)
        self.assertEqual(db.read_bytes(), before)
        self.assertEqual(list(db.parent.glob("*.building*")), [])

    def test_unicode_queries_reach_indexed_records(self):
        path = self.root / "memory" / "unicode.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\n"
            "schema_version: 1\nid: uni\ntype: lesson\nstatus: current\n"
            "importance: normal\nscope: repository\nrisk: low\ndurability: long_lived\n"
            "evidence: verified\ntopics: [café]\n"
            "created_at: 2026-09-17T00:00:00+00:00\n"
            "updated_at: 2026-09-17T00:00:00+00:00\nrelations: {}\n"
            "---\n\n# 认证重试 café\n\n## Summary\n\nRésumé of the 认证 retry behaviour.\n\n"
            "## Knowledge\n\nThe 认证 gateway retries cafés.\n",
            encoding="utf-8")
        for query in ("认证", "café", "résumé"):
            self.output.seek(0)
            self.output.truncate()
            rc = oldhand.search(self.root, query, history=False, limit=5,
                             scope=None, collection=None, log=False)
            self.assertEqual(rc, 0, query)
            self.assertIn("   id: uni\n", self.output.getvalue(), query)
            self.assertNotIn("No matching record", self.output.getvalue(), query)

    def test_search_filters_by_entry_type(self):
        self.record("lesson", type="lesson")
        self.record("decision", type="decision")
        rc = oldhand.search(self.root, "useful testing", history=False, limit=5,
                         scope=None, collection=None, log=False,
                         entry_type="decision")
        self.assertEqual(rc, 0)
        output = self.output.getvalue()
        self.assertIn("   id: decision\n", output)
        self.assertNotIn("   id: lesson\n", output)

    def test_search_filters_by_exact_status(self):
        self.record("current", status="current")
        self.record("resolved", status="resolved")
        rc = oldhand.search(self.root, "useful testing", history=False, limit=5,
                         scope=None, collection=None, log=False,
                         status="resolved")
        self.assertEqual(rc, 0)
        output = self.output.getvalue()
        self.assertIn("   id: resolved\n", output)
        self.assertNotIn("   id: current\n", output)

    def test_search_filters_by_exact_importance(self):
        self.record("normal", importance="normal")
        self.record("critical", importance="critical")
        rc = oldhand.search(self.root, "useful testing", history=False, limit=5,
                         scope=None, collection=None, log=False,
                         importance="critical", json_output=True)
        self.assertEqual(rc, 0)
        payload = json.loads(self.output.getvalue())
        self.assertEqual(payload["filters"]["importance"], "critical")
        self.assertEqual([item["id"] for item in payload["results"]], ["critical"])

    def test_search_filters_by_exact_topic(self):
        self.record("backend", topics=["API Gateway"])
        self.record("frontend", topics=["interface"])
        rc = oldhand.search(self.root, "useful testing", history=False, limit=5,
                         scope=None, collection=None, log=False,
                         topic="api gateway")
        self.assertEqual(rc, 0)
        output = self.output.getvalue()
        self.assertIn("   id: backend\n", output)
        self.assertNotIn("   id: frontend\n", output)

    def test_search_json_is_structured_for_hits_and_misses(self):
        self.record("decision", type="decision", topics=["API Gateway"])
        rc = oldhand.search(self.root, "useful testing", history=False, limit=5,
                         scope=None, collection=None, log=False,
                         entry_type="decision", topic="api gateway",
                         json_output=True)
        self.assertEqual(rc, 0)
        payload = json.loads(self.output.getvalue())
        self.assertEqual(payload["query"], "useful testing")
        self.assertEqual(payload["filters"]["type"], "decision")
        self.assertEqual(payload["filters"]["topic"], "api gateway")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["id"], "decision")
        self.assertEqual(payload["results"][0]["topics"], ["API Gateway"])

        self.output.seek(0)
        self.output.truncate()
        rc = oldhand.search(self.root, "term-that-does-not-exist", history=False,
                         limit=5, scope=None, collection=None, log=False,
                         json_output=True)
        self.assertEqual(rc, 0)
        payload = json.loads(self.output.getvalue())
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["searched"], 1)
        self.assertEqual(payload["results"], [])

    def test_explore_context_shares_guardrails_without_collapsing_diversity(self):
        self.record("guard", type="constraint", importance="critical",
                    risk="critical", durability="invariant")
        self.record("direction", type="decision", importance="normal")
        self.assertEqual(oldhand.explore_context(
            self.root, "useful testing", workers=3, history_branches=1,
            per_branch=5, json_output=True), 0)
        payload = json.loads(self.output.getvalue())
        self.assertEqual([item["id"] for item in payload["shared_guardrails"]], ["guard"])
        self.assertEqual(payload["branches"][0]["mode"], "history-guided")
        self.assertIn("direction", [item["id"] for item in payload["branches"][0]["records"]])
        self.assertEqual(payload["branches"][1]["mode"], "independent")
        self.assertEqual(payload["branches"][1]["records"], [])
        self.assertEqual(payload["branches"][2]["shared_guardrail_ids"], ["guard"])

    def test_show_json_returns_record_and_relationships(self):
        self.record("target", topics=["database"])
        self.record("source", type="decision", topics=["API Gateway"],
                    relations={"depends_on": ["target"]})
        oldhand.rebuild(self.root, quiet=True)
        rc = oldhand.show(self.root, "source", json_output=True)
        self.assertEqual(rc, 0)
        payload = json.loads(self.output.getvalue())
        self.assertEqual(payload["id"], "source")
        self.assertEqual(payload["type"], "decision")
        self.assertEqual(payload["topics"], ["API Gateway"])
        self.assertEqual(payload["relations"], {"depends_on": ["target"]})
        self.assertIn("Known facts.", payload["body"])

    def test_list_browses_active_records_with_filters_and_json(self):
        self.record("active-backend", type="lesson", topics=["backend"])
        self.record("retired-backend", type="decision", status="superseded",
                    topics=["backend"])
        self.record("active-frontend", type="decision", topics=["frontend"])
        rc = oldhand.list_records(self.root, history=False, limit=10,
                               entry_type="lesson", topic="backend",
                               collection=None, json_output=False)
        self.assertEqual(rc, 0)
        output = self.output.getvalue()
        self.assertIn("active-backend", output)
        self.assertNotIn("retired-backend", output)
        self.assertNotIn("active-frontend", output)

        self.output.seek(0)
        self.output.truncate()
        rc = oldhand.list_records(self.root, history=True, limit=1,
                               entry_type=None, topic="backend",
                               collection=None, json_output=True)
        self.assertEqual(rc, 0)
        payload = json.loads(self.output.getvalue())
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["returned"], 1)
        self.assertEqual(len(payload["records"]), 1)

    def test_list_filters_by_exact_status(self):
        self.record("current", status="current")
        self.record("retired", status="deprecated")
        rc = oldhand.list_records(self.root, history=False, limit=10,
                               entry_type=None, topic=None, collection=None,
                               json_output=True, status="deprecated")
        self.assertEqual(rc, 0)
        payload = json.loads(self.output.getvalue())
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["records"][0]["id"], "retired")
        self.assertEqual(payload["filters"]["status"], "deprecated")

    def test_list_filters_by_exact_importance(self):
        self.record("normal", importance="normal")
        self.record("critical", importance="critical")
        rc = oldhand.list_records(self.root, history=False, limit=10,
                               entry_type=None, topic=None, collection=None,
                               json_output=True, importance="critical")
        self.assertEqual(rc, 0)
        payload = json.loads(self.output.getvalue())
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["records"][0]["id"], "critical")
        self.assertEqual(payload["filters"]["importance"], "critical")

    def test_backlinks_reports_both_directions(self):
        self.record("center", relations={"depends_on": ["target"]})
        self.record("source", relations={"related_to": ["center"]})
        self.record("target")
        self.assertEqual(oldhand.backlinks(self.root, "center", json_output=True), 0)
        payload = json.loads(self.output.getvalue())
        self.assertEqual([(e["type"], e["id"]) for e in payload["incoming"]],
                         [("related_to", "source")])
        self.assertEqual([(e["type"], e["id"]) for e in payload["outgoing"]],
                         [("depends_on", "target")])

    def test_rename_updates_id_and_all_backlinks(self):
        target = self.record("old")
        source = self.record("source", relations={"depends_on": ["old"]})
        self.assertEqual(oldhand.rename_record_id(self.root, "old", "stable.id"), 0)
        target_meta = yaml.safe_load(target.read_text(encoding="utf-8").split("---\n")[1])
        source_meta = yaml.safe_load(source.read_text(encoding="utf-8").split("---\n")[1])
        self.assertEqual(target_meta["id"], "stable.id")
        self.assertEqual(source_meta["relations"]["depends_on"], ["stable.id"])
        records, errors, _ = oldhand.validate_records(self.root)
        self.assertFalse(errors)
        self.assertIn("stable.id", {record["meta"]["id"] for record in records})

    def test_rename_rejects_collision_without_changes(self):
        old = self.record("old")
        self.record("taken")
        before = old.read_bytes()
        self.assertEqual(oldhand.rename_record_id(self.root, "old", "taken"), 1)
        self.assertEqual(old.read_bytes(), before)

    def test_topic_add_and_remove_preserve_nonempty_topics(self):
        path = self.record("record", topics=["testing"])
        self.assertEqual(oldhand.curate_topic(self.root, "record", add="API Gateway"), 0)
        meta = yaml.safe_load(path.read_text(encoding="utf-8").split("---\n")[1])
        self.assertEqual(meta["topics"], ["testing", "API Gateway"])
        self.assertEqual(oldhand.curate_topic(self.root, "record", remove="api-gateway"), 0)
        self.assertEqual(oldhand.curate_topic(self.root, "record", remove="testing"), 1)

    def test_classify_updates_multiple_metadata_fields(self):
        path = self.record("record")
        self.assertEqual(oldhand.classify_record(
            self.root, "record", importance="critical", risk="high",
            durability="invariant", evidence="observed"), 0)
        meta = yaml.safe_load(path.read_text(encoding="utf-8").split("---\n")[1])
        self.assertEqual(
            {key: meta[key] for key in ("importance", "risk", "durability", "evidence")},
            {"importance": "critical", "risk": "high",
             "durability": "invariant", "evidence": "observed"})

    def test_classify_requires_a_change(self):
        self.record("record")
        self.assertEqual(oldhand.classify_record(self.root, "record"), 2)

    def test_compact_dry_run_then_retires_sources(self):
        target = self.record("target")
        first = self.record("first")
        second = self.record("second")
        before = {path: path.read_bytes() for path in (target, first, second)}
        self.assertEqual(oldhand.compact_records(
            self.root, "target", ["first", "second"], True, True), 0)
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.output.seek(0)
        self.output.truncate()
        self.assertEqual(oldhand.compact_records(
            self.root, "target", ["first", "second"], False, True), 0)
        target_meta = yaml.safe_load(target.read_text(encoding="utf-8").split("---\n")[1])
        self.assertEqual(target_meta["relations"]["supersedes"], ["first", "second"])
        for path in (first, second):
            meta = yaml.safe_load(path.read_text(encoding="utf-8").split("---\n")[1])
            self.assertEqual(meta["status"], "superseded")
            self.assertIn("Known facts.", path.read_text(encoding="utf-8"))

    def test_start_discovery_run_is_canonical_and_collision_safe(self):
        self.assertEqual(oldhand.experience.start_run(
            self.root, "Tune planner", "bench-v2", "manual", "minimize", 3,
            "planner-run", "git:abc", True), 0)
        receipt = json.loads(self.output.getvalue())
        self.assertEqual(receipt["id"], "planner-run")
        path = self.root / receipt["path"]
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["task"], "Tune planner")
        self.assertEqual(payload["goal"], "minimize")
        self.assertEqual(payload["max_workers"], 3)
        self.assertEqual(payload["nodes"], [])
        self.output.seek(0)
        self.output.truncate()
        self.assertEqual(oldhand.experience.start_run(
            self.root, "Again", "bench-v2", "manual", run_id="planner-run"), 1)
        self.assertEqual(oldhand.experience.start_run(
            self.root, "", "bench-v2", "manual", run_id="empty"), 2)

    def test_add_attempt_builds_a_tree_and_enforces_one_continuation(self):
        oldhand.experience.start_run(self.root, "Tune", "bench", "manual", run_id="run")
        self.assertEqual(oldhand.experience.add_attempt(
            self.root, "run", "branch-a", "root", "Try an index"), 0)
        self.assertEqual(oldhand.experience.add_attempt(
            self.root, "run", "refine-a", "branch-a", "Tune selectivity"), 0)
        self.assertEqual(oldhand.experience.add_attempt(
            self.root, "run", "other-a", "branch-a", "Duplicate continuation"), 1)
        self.assertEqual(oldhand.experience.add_attempt(
            self.root, "run", "missing", "unknown", "Bad parent"), 1)
        run = oldhand.experience.load_run(self.root, "run")
        self.assertEqual([(node["id"], node["parent_id"]) for node in run["nodes"]],
                         [("branch-a", "root"), ("refine-a", "branch-a")])

    def test_root_is_reserved_as_the_structural_attempt_id(self):
        oldhand.experience.start_run(self.root, "Tune", "bench", "manual", run_id="run")
        path = oldhand.experience.run_path(self.root, "run")
        baseline = path.read_bytes()
        self.assertEqual(oldhand.experience.add_attempt(
            self.root, "run", "root", "root", "Ambiguous"), 2)
        self.assertEqual(path.read_bytes(), baseline)

        malformed = oldhand.experience.load_run(self.root, "run")
        malformed["nodes"] = [{
            "id": "root", "parent_id": "root", "created_order": 1,
            "proposal": "Ambiguous", "created_at": malformed["created_at"],
            "evaluation": None,
        }]
        errors = oldhand.experience.validate_run_payload(malformed, "trace")
        self.assertTrue(any("reserved" in error for error in errors))

    def test_evaluate_attempt_records_grounded_outcome_once(self):
        oldhand.experience.start_run(self.root, "Tune", "bench", "manual", run_id="run")
        oldhand.experience.add_attempt(self.root, "run", "a", "root", "Try it")
        self.assertEqual(oldhand.experience.evaluate_attempt(
            self.root, "run", "a", 8.5, True, "success", 2, 1500,
            "results/a.json", True), 0)
        evaluation = oldhand.experience.load_run(self.root, "run")["nodes"][0]["evaluation"]
        self.assertEqual(evaluation["score"], 8.5)
        self.assertTrue(evaluation["correct"])
        self.assertEqual((evaluation["cost"], evaluation["duration_ms"]), (2, 1500))
        self.assertEqual(oldhand.experience.evaluate_attempt(
            self.root, "run", "a", 9, True, "success"), 1)

    def test_evaluate_attempt_rejects_noncanonical_numbers_before_write(self):
        oldhand.experience.start_run(self.root, "Tune", "bench", "manual", run_id="run")
        oldhand.experience.add_attempt(self.root, "run", "a", "root", "Try it")
        path = oldhand.experience.run_path(self.root, "run")
        baseline = path.read_bytes()
        invalid = (
            (True, 1, 0), (float("nan"), 1, 0), (float("inf"), 1, 0),
            (1.0, 1.5, 0), (1.0, True, 0), (1.0, 1, float("inf")),
        )
        for score, cost, duration in invalid:
            with self.subTest(score=score, cost=cost, duration=duration):
                self.assertEqual(oldhand.experience.evaluate_attempt(
                    self.root, "run", "a", score, True, "success",
                    cost=cost, duration_ms=duration), 2)
                self.assertEqual(path.read_bytes(), baseline)

    def test_evaluate_attempt_rejects_invalid_result_semantics(self):
        oldhand.experience.start_run(self.root, "Tune", "bench", "manual", run_id="run")
        oldhand.experience.add_attempt(self.root, "run", "a", "root", "Try it")
        path = oldhand.experience.run_path(self.root, "run")
        baseline = path.read_bytes()
        self.assertEqual(oldhand.experience.evaluate_attempt(
            self.root, "run", "a", 1, "yes", "success"), 2)
        self.assertEqual(oldhand.experience.evaluate_attempt(
            self.root, "run", "a", 1, True, "passed"), 2)
        self.assertEqual(path.read_bytes(), baseline)

    def test_mutators_reject_trace_identity_mismatch_without_writing(self):
        oldhand.experience.start_run(
            self.root, "Tune", "bench", "breadth", run_id="run")
        path = oldhand.experience.run_path(self.root, "run")
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["id"] = "other"
        path.write_text(json.dumps(payload), encoding="utf-8")
        baseline = path.read_bytes()
        self.assertEqual(oldhand.experience.add_attempt(
            self.root, "run", "a", "root", "proposal"), 1)
        self.assertEqual(path.read_bytes(), baseline)
        self.assertIn("does not match its filename", self.errors.getvalue())

    def test_finish_requires_evaluations_and_validates_trace(self):
        oldhand.experience.start_run(self.root, "Tune", "bench", "manual", run_id="run")
        oldhand.experience.add_attempt(self.root, "run", "a", "root", "Try it")
        self.assertEqual(oldhand.experience.finish_run(self.root, "run"), 1)
        oldhand.experience.evaluate_attempt(self.root, "run", "a", 8, True, "success")
        self.assertEqual(oldhand.experience.finish_run(self.root, "run", True), 0)
        run = oldhand.experience.load_run(self.root, "run")
        self.assertEqual(run["status"], "completed")
        self.assertIsNotNone(run["finished_at"])
        self.output.seek(0)
        self.output.truncate()
        self.assertEqual(oldhand.experience.validate_runs_cmd(self.root, None, True), 0)
        self.assertTrue(json.loads(self.output.getvalue())["valid"])

    def test_run_validation_reports_malformed_trace(self):
        path = self.root / "experience" / "runs" / "bad.json"
        path.parent.mkdir(parents=True)
        path.write_text('{"schema_version": 99, "id": "bad", "nodes": []}\n',
                        encoding="utf-8")
        _, errors = oldhand.experience.validate_runs(self.root)
        self.assertTrue(any("schema_version" in error for error in errors))
        self.assertTrue(any("missing fields" in error for error in errors))

    def test_trace_identity_and_evidence_time_are_canonical(self):
        oldhand.experience.start_run(self.root, "Tune", "bench", "manual", run_id="run-a")
        oldhand.experience.add_attempt(self.root, "run-a", "a", "root", "a")
        oldhand.experience.evaluate_attempt(
            self.root, "run-a", "a", 1, True, "success")
        oldhand.experience.finish_run(self.root, "run-a")
        copied = oldhand.experience.run_path(self.root, "run-b")
        copied.write_bytes(oldhand.experience.run_path(self.root, "run-a").read_bytes())
        _, errors = oldhand.experience.validate_runs(self.root)
        self.assertTrue(any("id must match filename" in error for error in errors))
        copied.unlink()

        run = oldhand.experience.load_run(self.root, "run-a")
        run["nodes"][0]["evaluation"]["evaluated_at"] = "2030-01-01T00:00:00+00:00"
        oldhand.experience._atomic_json(oldhand.experience.run_path(self.root, "run-a"), run)
        _, errors = oldhand.experience.validate_runs(self.root)
        self.assertTrue(any("evaluated_at is after finished_at" in error
                            for error in errors))

    def test_browse_runs_reports_aggregates_and_nested_tree(self):
        oldhand.experience.start_run(self.root, "Tune", "bench", "manual", run_id="run")
        oldhand.experience.add_attempt(self.root, "run", "a", "root", "Try index")
        oldhand.experience.evaluate_attempt(self.root, "run", "a", 8, True, "success", 2)
        oldhand.experience.add_attempt(self.root, "run", "b", "a", "Tune index")
        oldhand.experience.evaluate_attempt(self.root, "run", "b", 9, True, "success", 3)
        oldhand.experience.finish_run(self.root, "run")
        self.output.seek(0)
        self.output.truncate()
        self.assertEqual(oldhand.experience.list_runs(self.root, "completed", True), 0)
        catalog = json.loads(self.output.getvalue())
        self.assertEqual(catalog["runs"][0]["best_score"], 9)
        self.assertEqual(catalog["runs"][0]["total_cost"], 5)
        self.output.seek(0)
        self.output.truncate()
        self.assertEqual(oldhand.experience.show_run(self.root, "run", True), 0)
        detail = json.loads(self.output.getvalue())
        self.assertEqual(detail["tree"][0]["children"][0]["id"], "b")

    def test_replay_policies_reveal_only_selected_prefixes(self):
        oldhand.experience.start_run(self.root, "Tune", "bench", "manual", run_id="run")
        for node_id, parent, score in (("a", "root", 5), ("a2", "a", 8),
                                       ("b", "root", 7), ("b2", "b", 9)):
            oldhand.experience.add_attempt(self.root, "run", node_id, parent, node_id)
            oldhand.experience.evaluate_attempt(
                self.root, "run", node_id, score, True, "success")
        oldhand.experience.finish_run(self.root, "run")
        run = oldhand.experience.load_run(self.root, "run")
        breadth = oldhand.experience.replay_run(run, "breadth", 2)
        depth = oldhand.experience.replay_run(run, "depth", 2)
        self.assertEqual(breadth["revealed"], ["a", "b"])
        self.assertEqual(depth["revealed"], ["a", "a2"])
        self.assertEqual(depth["best_score"], 8)

    def test_replay_objective_balances_cost_and_parallelism(self):
        oldhand.experience.start_run(
            self.root, "Tune", "bench", "manual", workers=2, run_id="run")
        for node_id, parent, score in (("a", "root", 5), ("a2", "a", 8),
                                       ("b", "root", 7)):
            oldhand.experience.add_attempt(self.root, "run", node_id, parent, node_id)
            oldhand.experience.evaluate_attempt(
                self.root, "run", node_id, score, True, "success", cost=1)
        oldhand.experience.finish_run(self.root, "run")
        result = oldhand.experience.replay_run(
            oldhand.experience.load_run(self.root, "run"), "depth", 3,
            workers=2, beta_cost=1, beta_parallel=2)
        self.assertEqual(result["rounds"], 2)
        self.assertEqual(result["total_cost"], 3)
        self.assertEqual(result["parallelism"], 1.5)
        self.assertEqual(result["objective"], 8)

    def test_replay_fans_out_root_branches_in_one_worker_batch(self):
        oldhand.experience.start_run(
            self.root, "Tune", "bench", "breadth", workers=2, run_id="run")
        for node_id in ("a", "b"):
            oldhand.experience.add_attempt(
                self.root, "run", node_id, "root", f"Try {node_id}")
            oldhand.experience.evaluate_attempt(
                self.root, "run", node_id, 1, True, "success")
        oldhand.experience.finish_run(self.root, "run")
        result = oldhand.experience.replay_run(
            oldhand.experience.load_run(self.root, "run"), "breadth", 2, workers=2)
        self.assertEqual(result["revealed"], ["a", "b"])
        self.assertEqual(result["rounds"], 1)
        self.assertEqual(result["decisions"][0], {
            "round": 1, "selected": ["root", "root"], "revealed": ["a", "b"],
        })
        self.assertEqual(result["parallelism"], 2.0)

    def test_replay_oversized_budget_does_not_count_empty_rounds(self):
        oldhand.experience.start_run(
            self.root, "Tune", "bench", "breadth", workers=2, run_id="run")
        for node_id in ("a", "b"):
            oldhand.experience.add_attempt(self.root, "run", node_id, "root", node_id)
            oldhand.experience.evaluate_attempt(
                self.root, "run", node_id, 2, True, "success")
        oldhand.experience.finish_run(self.root, "run")
        result = oldhand.experience.replay_run(
            oldhand.experience.load_run(self.root, "run"), "breadth", 10,
            workers=2, beta_parallel=1)
        self.assertEqual(result["rounds"], 1)
        self.assertTrue(all(decision["revealed"] for decision in result["decisions"]))
        self.assertEqual(result["parallelism"], 2.0)
        self.assertEqual(result["objective"], 4.0)

    def test_replay_and_comparison_reject_nonfinite_coefficients(self):
        oldhand.experience.start_run(
            self.root, "Tune", "bench", "breadth", run_id="run")
        oldhand.experience.add_attempt(self.root, "run", "a", "root", "a")
        oldhand.experience.evaluate_attempt(
            self.root, "run", "a", 1, True, "success")
        oldhand.experience.finish_run(self.root, "run")
        run = oldhand.experience.load_run(self.root, "run")
        for invalid in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaisesRegex(ValueError, "finite and non-negative"):
                oldhand.experience.replay_run(run, "breadth", 1, beta_cost=invalid)
            self.assertEqual(oldhand.experience.compare_policies(
                self.root, ["breadth"], "breadth", 1, holdout=0,
                evaluator="bench", beta_parallel=invalid), 2)

    def test_score_greedy_explores_before_extending_incorrect_branch(self):
        for goal in ("maximize", "minimize"):
            with self.subTest(goal=goal):
                run_id = f"run-{goal}"
                oldhand.experience.start_run(
                    self.root, "Tune", "bench", "score-greedy", goal=goal,
                    run_id=run_id)
                for node_id, parent, correct in (
                        ("bad", "root", False), ("bad-child", "bad", True),
                        ("fresh", "root", True)):
                    oldhand.experience.add_attempt(
                        self.root, run_id, node_id, parent, node_id)
                    oldhand.experience.evaluate_attempt(
                        self.root, run_id, node_id, 1, correct, "success")
                oldhand.experience.finish_run(self.root, run_id)
                result = oldhand.experience.replay_run(
                    oldhand.experience.load_run(self.root, run_id),
                    "score-greedy", 2)
                self.assertEqual(result["revealed"], ["bad", "fresh"])

    def test_replay_minimize_goal_converts_quality(self):
        oldhand.experience.start_run(
            self.root, "Tune", "bench", "manual", goal="minimize", run_id="run")
        oldhand.experience.add_attempt(self.root, "run", "a", "root", "a")
        oldhand.experience.evaluate_attempt(self.root, "run", "a", 4, True, "success")
        oldhand.experience.finish_run(self.root, "run")
        result = oldhand.experience.replay_run(
            oldhand.experience.load_run(self.root, "run"), "depth", 1)
        self.assertEqual(result["best_score"], 4)
        self.assertEqual(result["quality"], -4)

    def test_policy_compare_includes_incumbent_and_holdout(self):
        for run_id, offset in (("run1", 0), ("run2", 1), ("run3", 2)):
            oldhand.experience.start_run(
                self.root, "Tune", "bench", "breadth", workers=1, run_id=run_id)
            for node_id, parent, score in (("a", "root", 5 + offset),
                                           ("a2", "a", 9 + offset),
                                           ("b", "root", 7 + offset)):
                oldhand.experience.add_attempt(self.root, run_id, node_id, parent, node_id)
                oldhand.experience.evaluate_attempt(
                    self.root, run_id, node_id, score, True, "success")
            oldhand.experience.finish_run(self.root, run_id)
        self.output.seek(0)
        self.output.truncate()
        self.assertEqual(oldhand.experience.compare_policies(
            self.root, ["depth"], "breadth", 2, holdout=1,
            evaluator="bench", json_output=True), 0)
        payload = json.loads(self.output.getvalue())
        self.assertEqual(payload["holdout_runs"], ["run3"])
        self.assertEqual({item["policy"] for item in payload["comparisons"]},
                         {"breadth", "depth"})
        winner = payload["comparisons"][0]
        self.assertEqual(winner["policy"], "depth")
        self.assertFalse(winner["incumbent"])
        self.assertEqual(oldhand.experience.compare_policies(
            self.root, ["depth"], "breadth", 2, holdout=1,
            evaluator="bench", beta_cost=-1), 2)

    def test_policy_compare_never_selects_on_holdout(self):
        for run_id, scores in (("run1", (5, 9, 7)), ("run2", (5, 6, 10))):
            oldhand.experience.start_run(
                self.root, "Tune", "bench", "breadth", workers=1, run_id=run_id)
            for (node_id, parent), score in zip(
                    (("a", "root"), ("a2", "a"), ("b", "root")), scores):
                oldhand.experience.add_attempt(
                    self.root, run_id, node_id, parent, node_id)
                oldhand.experience.evaluate_attempt(
                    self.root, run_id, node_id, score, True, "success")
            oldhand.experience.finish_run(self.root, run_id)
        self.output.seek(0)
        self.output.truncate()
        self.assertEqual(oldhand.experience.compare_policies(
            self.root, ["depth"], "breadth", 2, holdout=1,
            evaluator="bench", json_output=True), 0)
        payload = json.loads(self.output.getvalue())
        self.assertEqual(payload["ranking_basis"], "train")
        self.assertEqual(payload["comparisons"][0]["policy"], "depth")
        by_policy = {item["policy"]: item for item in payload["comparisons"]}
        self.assertGreater(by_policy["breadth"]["holdout"]["mean_objective"],
                           by_policy["depth"]["holdout"]["mean_objective"])

    def test_policy_compare_orders_holdout_by_timestamp_instant(self):
        timestamps = (
            ("earlier-local", "2026-01-01T10:00:00+05:30"),
            ("later-utc", "2026-01-01T06:00:00+00:00"),
        )
        for run_id, timestamp in timestamps:
            oldhand.experience.start_run(
                self.root, "Tune", "bench", "breadth", run_id=run_id)
            oldhand.experience.add_attempt(self.root, run_id, "a", "root", "a")
            oldhand.experience.evaluate_attempt(
                self.root, run_id, "a", 1, True, "success")
            oldhand.experience.finish_run(self.root, run_id)
            run = oldhand.experience.load_run(self.root, run_id)
            run["created_at"] = timestamp
            run["updated_at"] = timestamp
            run["finished_at"] = timestamp
            run["nodes"][0]["created_at"] = timestamp
            run["nodes"][0]["evaluation"]["evaluated_at"] = timestamp
            oldhand.experience._atomic_json(oldhand.experience.run_path(self.root, run_id), run)
        self.output.seek(0)
        self.output.truncate()
        self.assertEqual(oldhand.experience.compare_policies(
            self.root, ["breadth"], "breadth", 1, holdout=1,
            evaluator="bench", json_output=True), 0)
        payload = json.loads(self.output.getvalue())
        self.assertEqual(payload["train_runs"], ["earlier-local"])
        self.assertEqual(payload["holdout_runs"], ["later-utc"])

    def test_policy_compare_orders_holdout_by_completion_time(self):
        timelines = (
            ("run-a", "2026-01-01T00:00:00+00:00", "2026-01-10T00:00:00+00:00"),
            ("run-b", "2026-01-05T00:00:00+00:00", "2026-01-06T00:00:00+00:00"),
        )
        for run_id, created, finished in timelines:
            oldhand.experience.start_run(
                self.root, "Tune", "bench", "breadth", run_id=run_id)
            oldhand.experience.add_attempt(self.root, run_id, "a", "root", "a")
            oldhand.experience.evaluate_attempt(
                self.root, run_id, "a", 1, True, "success")
            oldhand.experience.finish_run(self.root, run_id)
            run = oldhand.experience.load_run(self.root, run_id)
            run["created_at"] = created
            run["finished_at"] = finished
            run["updated_at"] = finished
            run["nodes"][0]["created_at"] = created
            run["nodes"][0]["evaluation"]["evaluated_at"] = finished
            oldhand.experience._atomic_json(oldhand.experience.run_path(self.root, run_id), run)
        self.output.seek(0)
        self.output.truncate()
        self.assertEqual(oldhand.experience.compare_policies(
            self.root, ["breadth"], "breadth", 1, holdout=1,
            evaluator="bench", json_output=True), 0)
        payload = json.loads(self.output.getvalue())
        self.assertEqual(payload["train_runs"], ["run-b"])
        self.assertEqual(payload["holdout_runs"], ["run-a"])

    def test_policy_compare_ranks_success_coverage_before_mean(self):
        runs = (
            ("run1", ((5, True), (100, True), (60, True))),
            ("run2", ((5, False), (100, False), (60, True))),
        )
        for run_id, evaluations in runs:
            oldhand.experience.start_run(
                self.root, "Tune", "bench", "breadth", run_id=run_id)
            for (node_id, parent), (score, correct) in zip(
                    (("a", "root"), ("a2", "a"), ("b", "root")), evaluations):
                oldhand.experience.add_attempt(
                    self.root, run_id, node_id, parent, node_id)
                oldhand.experience.evaluate_attempt(
                    self.root, run_id, node_id, score, correct, "success")
            oldhand.experience.finish_run(self.root, run_id)
        self.output.seek(0)
        self.output.truncate()
        self.assertEqual(oldhand.experience.compare_policies(
            self.root, ["depth"], "breadth", 2, holdout=0,
            evaluator="bench", json_output=True), 0)
        comparisons = json.loads(self.output.getvalue())["comparisons"]
        self.assertEqual(comparisons[0]["policy"], "breadth")
        by_policy = {item["policy"]: item for item in comparisons}
        self.assertEqual(by_policy["breadth"]["train"]["scored_count"], 2)
        self.assertEqual(by_policy["depth"]["train"]["scored_count"], 1)
        self.assertGreater(by_policy["depth"]["train"]["mean_objective"],
                           by_policy["breadth"]["train"]["mean_objective"])

    def test_policy_compare_rejects_mixed_goals(self):
        for run_id, goal in (("run-max", "maximize"), ("run-min", "minimize")):
            oldhand.experience.start_run(
                self.root, "Tune", "bench", "breadth", goal=goal, run_id=run_id)
            oldhand.experience.add_attempt(self.root, run_id, "a", "root", "a")
            oldhand.experience.evaluate_attempt(
                self.root, run_id, "a", 1, True, "success")
            oldhand.experience.finish_run(self.root, run_id)
        self.assertEqual(oldhand.experience.compare_policies(
            self.root, ["depth"], "breadth", 1, holdout=0,
            evaluator="bench"), 1)
        self.assertIn("Mixed goals", self.errors.getvalue())
        self.errors.seek(0)
        self.errors.truncate()
        self.output.seek(0)
        self.output.truncate()
        self.assertEqual(oldhand.experience.compare_policies(
            self.root, ["depth"], "breadth", 1, holdout=0,
            evaluator="bench", json_output=True, goal="minimize"), 0)
        self.assertEqual(json.loads(self.output.getvalue())["goal"], "minimize")

    def test_run_identity_fields_are_canonical(self):
        self.assertEqual(oldhand.experience.start_run(
            self.root, " Tune ", " bench ", " manual ", run_id="run"), 0)
        run = oldhand.experience.load_run(self.root, "run")
        self.assertEqual((run["task"], run["evaluator"], run["policy"]),
                         ("Tune", "bench", "manual"))
        run["evaluator"] = " bench "
        self.assertTrue(any("surrounding whitespace" in error for error in
                            oldhand.experience.validate_run_payload(run, "trace")))

    def test_run_distill_builds_verified_record_with_provenance(self):
        oldhand.experience.start_run(self.root, "Tune", "bench-v2", "depth", run_id="run")
        oldhand.experience.add_attempt(
            self.root, "run", "a", "root", "Use an indexed lookup", "git:abc")
        oldhand.experience.evaluate_attempt(
            self.root, "run", "a", 9, True, "success", 2, 150,
            "results/a.json")
        oldhand.experience.finish_run(self.root, "run")
        self.output.seek(0)
        self.output.truncate()
        args = argparse.Namespace(
            run_id="run", node_id="a", id="indexed-lookup", title="Use indexed lookup",
            entry_type="lesson", importance="normal", topics="database,performance",
            summary=None, scope="subsystem", risk="low", durability="long_lived",
            collection=None, dry_run=True, json_output=True)
        self.assertEqual(oldhand.distill_run(self.root, args), 0)
        content = json.loads(self.output.getvalue())["content"]
        self.assertIn("evidence: verified", content)
        self.assertIn("experience/runs/run.json (attempt `a`)", content)
        self.assertIn("Evaluator: bench-v2", content)

    def test_topics_lists_active_topic_counts_as_json(self):
        self.record("one", topics=["Backend", "testing"])
        self.record("two", topics=["Backend"])
        self.record("old", status="deprecated", topics=["retired-only"])
        rc = oldhand.list_topics(self.root, limit=1, collection=None, json_output=True)
        self.assertEqual(rc, 0)
        payload = json.loads(self.output.getvalue())
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["returned"], 1)
        self.assertEqual(payload["topics"][0]["key"], "backend")
        self.assertEqual(payload["topics"][0]["record_count"], 2)

    def test_collections_reports_record_and_topic_counts(self):
        self.record("active", topics=["backend", "testing"])
        self.record("old", status="deprecated", topics=["legacy"])
        rc = oldhand.list_collections(self.root, json_output=True)
        self.assertEqual(rc, 0)
        payload = json.loads(self.output.getvalue())
        self.assertEqual(payload["count"], 1)
        collection = payload["collections"][0]
        self.assertEqual(collection["record_count"], 2)
        self.assertEqual(collection["active_record_count"], 1)
        self.assertEqual(collection["topic_count"], 3)

    def test_relate_adds_one_valid_relationship(self):
        source = self.record("source")
        self.record("target")
        self.assertEqual(oldhand.relate(self.root, "source", "depends_on", "target"), 0)
        meta = yaml.safe_load(source.read_text(encoding="utf-8").split("---\n")[1])
        self.assertEqual(meta["relations"], {"depends_on": ["target"]})
        self.assertNotEqual(str(meta["updated_at"]), "2026-09-17 00:00:00+00:00")

        self.assertEqual(oldhand.relate(self.root, "source", "depends_on", "target"), 0)
        meta = yaml.safe_load(source.read_text(encoding="utf-8").split("---\n")[1])
        self.assertEqual(meta["relations"], {"depends_on": ["target"]})

    def test_relate_rejects_unknown_and_self_targets(self):
        source = self.record("source")
        before = source.read_bytes()
        self.assertEqual(oldhand.relate(self.root, "source", "depends_on", "missing"), 1)
        self.assertEqual(oldhand.relate(self.root, "source", "depends_on", "source"), 1)
        self.assertEqual(source.read_bytes(), before)

    def test_unrelate_removes_relationship_and_rejects_missing(self):
        source = self.record("source", relations={"depends_on": ["target"]})
        self.record("target")
        self.assertEqual(oldhand.unrelate(self.root, "source", "depends_on", "target"), 0)
        meta = yaml.safe_load(source.read_text(encoding="utf-8").split("---\n")[1])
        self.assertEqual(meta["relations"], {})
        after = source.read_bytes()
        self.assertEqual(oldhand.unrelate(self.root, "source", "depends_on", "target"), 1)
        self.assertEqual(source.read_bytes(), after)

    def test_supersede_updates_both_records_atomically(self):
        old = self.record("old")
        new = self.record("new")
        self.assertEqual(oldhand.supersede_record(self.root, "old", "new"), 0)
        old_meta = yaml.safe_load(old.read_text(encoding="utf-8").split("---\n")[1])
        new_meta = yaml.safe_load(new.read_text(encoding="utf-8").split("---\n")[1])
        self.assertEqual(old_meta["status"], "superseded")
        self.assertEqual(new_meta["relations"], {"supersedes": ["old"]})
        valid, errors, _ = oldhand.validate_records(self.root)
        self.assertEqual(len(valid), 2)
        self.assertEqual(errors, [])

    def test_supersede_unknown_id_changes_nothing(self):
        old = self.record("old")
        before = old.read_bytes()
        self.assertEqual(oldhand.supersede_record(self.root, "old", "missing"), 1)
        self.assertEqual(old.read_bytes(), before)

    def test_status_command_manages_non_supersession_states(self):
        path = self.record("record")
        for status in ("resolved", "historical", "deprecated", "current"):
            self.assertEqual(oldhand.set_record_status(self.root, "record", status), 0)
            meta = yaml.safe_load(path.read_text(encoding="utf-8").split("---\n")[1])
            self.assertEqual(meta["status"], status)
        before = path.read_bytes()
        self.assertEqual(oldhand.set_record_status(self.root, "record", "superseded"), 1)
        self.assertEqual(path.read_bytes(), before)

    def test_new_record_topics_round_trip(self):
        args = argparse.Namespace(
            title="A topic test", type="lesson", importance="normal",
            topics="on, null, api: gateway, *backend, café",
            status="current", scope="subsystem", risk="low",
            durability="situational", evidence="documented",
            summary=None, knowledge=None, verification=None, collection=None)
        rc = oldhand.new_record(self.root, args)
        self.assertEqual(rc, 0)
        path = self.root / "memory" / "lessons" / "a-topic-test.md"
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count("topics:"), 1, text)
        meta = yaml.safe_load(text.split("---\n")[1])
        self.assertEqual(meta["topics"],
                         ["on", "null", "api: gateway", "*backend", "café"])
        valid, errors, _ = oldhand.validate_records(self.root)
        self.assertEqual(len(valid), 1)
        self.assertEqual(errors, [])

    def test_init_archive_creates_scaffold_and_refuses_overwrite(self):
        target = self.root / "knowledge"
        self.assertEqual(oldhand.init_archive(target, json_output=True), 0)
        payload = json.loads(self.output.getvalue())
        self.assertTrue(payload["created"])
        self.assertEqual(payload["root"], str(target))
        self.assertTrue((target / "memory" / "README.md").exists())
        self.assertTrue((target / ".oldhand" / "oldhand.db").exists())

        self.output.seek(0)
        self.output.truncate()
        self.assertEqual(oldhand.init_archive(target, json_output=False), 1)

    def test_new_record_json_output(self):
        args = argparse.Namespace(
            title="JSON creation", type="lesson", importance="normal",
            topics="automation", status="current", scope="subsystem", risk="low",
            durability="situational", evidence="documented", summary=None,
            knowledge=None, verification=None, collection=None,
            json_output=True, dry_run=False)
        rc = oldhand.new_record(self.root, args)
        self.assertEqual(rc, 0)
        payload = json.loads(self.output.getvalue())
        self.assertTrue(payload["created"])
        self.assertFalse(payload["dry_run"])
        self.assertEqual(payload["id"], "lore_json_creation")
        self.assertEqual(payload["path"], "memory/lessons/json-creation.md")

    def test_new_record_accepts_explicit_portable_id(self):
        args = argparse.Namespace(
            id="gateway.retry-policy_v2", title="Explicit identity", type="lesson",
            importance="normal", topics="automation", status="current",
            scope="subsystem", risk="low", durability="situational",
            evidence="documented", summary=None, knowledge=None, verification=None,
            collection=None, json_output=True, dry_run=False)
        self.assertEqual(oldhand.new_record(self.root, args), 0)
        payload = json.loads(self.output.getvalue())
        self.assertEqual(payload["id"], "gateway.retry-policy_v2")

        self.output.seek(0)
        self.output.truncate()
        self.assertEqual(oldhand.new_record(self.root, args), 1)
        args.id = "invalid id/with spaces"
        self.assertEqual(oldhand.new_record(self.root, args), 2)

    def test_new_record_dry_run_writes_nothing(self):
        args = argparse.Namespace(
            title="Preview only", type="lesson", importance="normal",
            topics="automation", status="current", scope="subsystem", risk="low",
            durability="situational", evidence="documented", summary="Preview summary.",
            knowledge="Preview knowledge.", verification="Preview verification.",
            collection=None, json_output=False, dry_run=True)
        rc = oldhand.new_record(self.root, args)
        self.assertEqual(rc, 0)
        self.assertFalse((self.root / "memory" / "lessons" / "preview-only.md").exists())
        output = self.output.getvalue()
        self.assertTrue(output.startswith("---\n"))
        self.assertIn("id: lore_preview_only", output)
        self.assertIn("Preview summary.", output)

    def test_metrics_full_on_empty_and_retired_archives(self):
        for seed in (None, "retired"):
            self.output.seek(0)
            self.output.truncate()
            self.errors.seek(0)
            self.errors.truncate()
            for child in self.root.iterdir():
                if child.name in (".oldhand", "metrics"):
                    continue
                if child.is_file():
                    child.unlink()
                else:
                    import shutil
                    shutil.rmtree(child)
            if seed:
                self.record("retired-one", status="superseded")
            rc = oldhand.metrics(self.root, full=True, export=None)
            self.assertEqual(rc, 0, self.errors.getvalue())
            self.assertIn("findability", self.output.getvalue())
            self.assertIn("N/A", self.output.getvalue())
            self.assertNotIn("Traceback", self.output.getvalue())
            self.assertNotIn("TypeError", self.output.getvalue())

    def test_metrics_export_rejects_unexpected_field_names(self):
        self.record("safe")
        snapshot = oldhand.collect_metrics(self.root)
        snapshot["archive"]["secret-client-codename"] = 1
        metrics_path = self.root / "metrics" / "daily.jsonl"
        metrics_path.parent.mkdir(parents=True)
        metrics_path.write_text(json.dumps(snapshot) + "\n", encoding="utf-8")
        export = self.root / "export.json"
        self.assertEqual(oldhand.metrics(self.root, full=False, export=str(export)), 1)
        self.assertFalse(export.exists())
        self.assertIn("secret-client-codename", self.errors.getvalue())

        self.output.seek(0)
        self.output.truncate()
        self.errors.seek(0)
        self.errors.truncate()
        snapshot["archive"].pop("secret-client-codename")
        metrics_path.write_text(json.dumps(snapshot) + "\n", encoding="utf-8")
        self.assertEqual(oldhand.metrics(self.root, full=False, export=str(export)), 0)
        self.assertEqual(oldhand._audit_export(json.loads(export.read_text())), [])

    def test_metrics_export_cannot_overwrite_daily_history(self):
        self.record("safe")
        oldhand.record_daily_metrics(self.root)
        history = oldhand._metrics_path(self.root)
        baseline = history.read_bytes()
        self.assertEqual(oldhand.metrics(
            self.root, full=False, export=str(history.parent / ".." / "metrics"
                                              / "daily.jsonl")), 1)
        self.assertEqual(history.read_bytes(), baseline)
        self.assertIn("daily metrics history", self.errors.getvalue())

    def test_metrics_export_ignores_structurally_invalid_history_rows(self):
        self.record("safe")
        valid = oldhand.collect_metrics(self.root)
        history = oldhand._metrics_path(self.root)
        history.parent.mkdir(parents=True, exist_ok=True)
        history.write_text("42\n[]\n{\"schema\": 1}\n" + json.dumps(valid) + "\n",
                           encoding="utf-8")
        export = self.root / "export.json"
        self.assertEqual(oldhand.metrics(self.root, full=False, export=str(export)), 0)
        bundle = json.loads(export.read_text())
        self.assertEqual(bundle["days"], 1)
        self.assertEqual(bundle["history"], [valid])
        self.assertIn("ignored 3 invalid", self.errors.getvalue())

    def test_metrics_export_omits_nonfinite_history_numbers(self):
        self.record("safe")
        valid = oldhand.collect_metrics(self.root)
        history = oldhand._metrics_path(self.root)
        history.parent.mkdir(parents=True, exist_ok=True)
        poisoned = json.dumps(valid).replace('"records": 1', '"records": NaN')
        history.write_text(poisoned + "\n" + json.dumps(valid) + "\n",
                           encoding="utf-8")
        export = self.root / "export.json"
        self.assertEqual(oldhand.metrics(self.root, full=False, export=str(export)), 0)
        bundle = json.loads(
            export.read_text(), parse_constant=oldhand._reject_json_constant)
        self.assertEqual(bundle["days"], 1)
        self.assertIn("ignored 1 invalid", self.errors.getvalue())

    def test_metrics_export_collapses_duplicate_dates_to_latest(self):
        self.record("safe")
        morning = oldhand.collect_metrics(self.root)
        morning["captured_at"] = "2026-09-17T09:00:00+00:00"
        evening = json.loads(json.dumps(morning))
        evening["captured_at"] = "2026-09-17T17:00:00+00:00"
        evening["retrieval"]["searches"] = 2
        history = oldhand._metrics_path(self.root)
        history.parent.mkdir(parents=True, exist_ok=True)
        history.write_text(json.dumps(evening) + "\n" + json.dumps(morning) + "\n",
                           encoding="utf-8")
        export = self.root / "export.json"
        self.assertEqual(oldhand.metrics(self.root, False, str(export)), 0)
        bundle = json.loads(export.read_text())
        self.assertEqual(bundle["days"], 1)
        self.assertEqual(bundle["history"][0]["retrieval"]["searches"], 2)
        self.assertIn("collapsed 1 duplicate", self.errors.getvalue())

    def test_metrics_export_is_atomic_and_reports_publication_failure(self):
        self.record("safe")
        oldhand.rebuild(self.root, quiet=True)
        export = self.root / "export.json"
        export.write_text("prior\n", encoding="utf-8")
        with mock.patch.object(oldhand.os, "replace", side_effect=OSError("disk full")):
            self.assertEqual(oldhand.metrics(self.root, False, str(export)), 1)
        self.assertEqual(export.read_text(encoding="utf-8"), "prior\n")
        self.assertFalse(list(self.root.glob("export.json.updating.*")))
        self.assertIn("Cannot write metrics export", self.errors.getvalue())

    def test_metrics_ignore_malformed_events_and_bound_open_rate(self):
        self.record("returned")
        self.record("shown-only")
        oldhand.rebuild(self.root, quiet=True)
        log = self.root / ".oldhand" / "retrieval.jsonl"
        events = [
            {"at": "2026-09-18T10:00:00+00:00", "action": "search",
             "query": "private client codename", "returned": ["returned"]},
            {"at": "2026-09-18T10:01:00+00:00", "action": "show",
             "query": "returned", "returned": ["returned"]},
            {"at": "2026-09-18T10:02:00+00:00", "action": "show",
             "query": "shown-only", "returned": ["shown-only"]},
            ["not", "an", "event"],
            {"at": "2026-09-18T10:03:00+00:00", "action": "search",
             "query": "bad", "returned": [["unhashable"]]},
        ]
        log.write_text("".join(json.dumps(event) + "\n" for event in events),
                       encoding="utf-8")
        retrieval = oldhand.collect_metrics(self.root)["retrieval"]
        self.assertEqual((retrieval["searches"], retrieval["shows"]), (1, 2))
        self.assertEqual(retrieval["coverage"], 0.5)
        self.assertEqual(retrieval["open_rate"], 1.0)
        self.assertLessEqual(retrieval["open_rate"], 1.0)

    def test_daily_metrics_upserts_today_atomically(self):
        self.record("safe")
        path = oldhand._metrics_path(self.root)
        path.parent.mkdir(parents=True)
        yesterday = oldhand.collect_metrics(self.root)
        yesterday["captured_at"] = "2026-09-17T10:00:00+00:00"
        stale_today = oldhand.collect_metrics(self.root)
        path.write_text(json.dumps(yesterday) + "\n" + json.dumps(stale_today) + "\n",
                        encoding="utf-8")
        log = self.root / ".oldhand" / "retrieval.jsonl"
        log.write_text(json.dumps({
            "at": "2026-09-18T10:00:00+00:00", "action": "search",
            "query": "private", "returned": ["safe"],
        }) + "\n", encoding="utf-8")
        oldhand.record_daily_metrics(self.root)
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        today = oldhand.datetime.now().astimezone().strftime("%Y-%m-%d")
        self.assertEqual(sum(row["captured_at"][:10] == today for row in rows), 1)
        self.assertEqual(rows[-1]["retrieval"]["searches"], 1)

    def test_daily_metrics_canonicalizes_old_duplicate_dates(self):
        self.record("safe")
        old = oldhand.collect_metrics(self.root)
        old["captured_at"] = "2026-09-17T09:00:00+00:00"
        newer = json.loads(json.dumps(old))
        newer["captured_at"] = "2026-09-17T17:00:00+00:00"
        newer["retrieval"]["searches"] = 2
        path = oldhand._metrics_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(newer) + "\n" + json.dumps(old) + "\n")
        oldhand.record_daily_metrics(self.root)
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        old_rows = [row for row in rows if row["captured_at"].startswith("2026-09-17")]
        self.assertEqual(len(old_rows), 1)
        self.assertEqual(old_rows[0]["retrieval"]["searches"], 2)

    def test_selftest(self):
        self.assertEqual(oldhand.selftest(), 0)

    def test_setup_claude_dry_run_is_non_mutating_and_exact(self):
        target = self.root / ".claude" / "rules" / "oldhand.md"
        self.assertEqual(oldhand.setup_harness(self.root, "claude"), 0)
        self.assertFalse(target.exists())
        self.assertFalse((self.root / "metrics").exists())
        output = self.output.getvalue()
        self.assertIn("--- a/.claude/rules/oldhand.md", output)
        self.assertIn(oldhand.SETUP_START, output)
        self.assertIn("Dry run only", output)

    def test_setup_claude_apply_is_idempotent_and_undo_removes_only_owned_file(self):
        target = self.root / ".claude" / "rules" / "oldhand.md"
        self.assertEqual(oldhand.setup_harness(self.root, "claude", apply=True), 0)
        generated = target.read_text(encoding="utf-8")
        self.assertIn(oldhand.SETUP_GUIDANCE, generated)
        self.output.seek(0)
        self.output.truncate()
        self.assertEqual(oldhand.setup_harness(self.root, "claude", apply=True), 0)
        self.assertEqual(target.read_text(encoding="utf-8"), generated)
        self.assertIn("already up to date", self.output.getvalue())
        self.assertEqual(oldhand.setup_harness(self.root, "claude", apply=True, undo=True), 0)
        self.assertFalse(target.exists())

    def test_setup_preserves_existing_dedicated_file_and_cursor_rule_is_agent_requested(self):
        claude = self.root / ".claude" / "rules" / "oldhand.md"
        claude.parent.mkdir(parents=True)
        claude.write_text("# Existing team rule\n", encoding="utf-8")
        self.assertEqual(oldhand.setup_harness(self.root, "claude", apply=True), 1)
        self.assertEqual(claude.read_text(encoding="utf-8"), "# Existing team rule\n")

        cursor = self.root / ".cursor" / "rules" / "oldhand.mdc"
        self.assertEqual(oldhand.setup_harness(self.root, "cursor", apply=True), 0)
        rule = cursor.read_text(encoding="utf-8")
        self.assertIn("description:", rule)
        self.assertNotIn("alwaysApply:", rule)
        self.assertIn(oldhand.SETUP_START, rule)
        self.assertEqual(oldhand.setup_harness(self.root, "cursor", apply=True, undo=True), 0)
        self.assertFalse(cursor.exists())

    def test_setup_codex_and_opencode_require_existing_agents_and_preserve_it(self):
        agents = self.root / "AGENTS.md"
        self.assertEqual(oldhand.setup_harness(self.root, "codex", apply=True), 1)
        self.assertFalse(agents.exists())
        agents.write_text("# Team instructions\n\nKeep reviews focused.\n", encoding="utf-8")
        self.assertEqual(oldhand.setup_harness(self.root, "codex", apply=True), 0)
        updated = agents.read_text(encoding="utf-8")
        self.assertTrue(updated.startswith("# Team instructions"))
        self.assertEqual(updated.count(oldhand.SETUP_START), 1)
        self.assertEqual(oldhand.setup_harness(self.root, "opencode", apply=True), 0)
        self.assertEqual(agents.read_text(encoding="utf-8").count(oldhand.SETUP_START), 1)
        self.assertEqual(oldhand.setup_harness(self.root, "codex", apply=True, undo=True), 0)
        self.assertEqual(agents.read_text(encoding="utf-8"),
                         "# Team instructions\n\nKeep reviews focused.\n")

    def test_setup_refuses_malformed_markers_and_symlink_escape(self):
        target = self.root / "AGENTS.md"
        target.write_text(oldhand.SETUP_START + "\n", encoding="utf-8")
        self.assertEqual(oldhand.setup_harness(self.root, "codex", apply=True), 1)
        self.assertEqual(target.read_text(encoding="utf-8"), oldhand.SETUP_START + "\n")

        outside = Path(self.temp.name).parent / "oldhand-setup-outside"
        outside.mkdir(exist_ok=True)
        link = self.root / ".claude"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")
        self.assertEqual(oldhand.setup_harness(self.root, "claude", apply=True), 1)
        self.assertFalse((outside / "rules" / "oldhand.md").exists())

    def test_setup_cli_default_dry_run_does_not_create_metrics(self):
        with mock.patch.object(sys, "argv", [str(SOURCE), "--root", str(self.root),
                                               "setup", "cursor"]):
            self.assertEqual(oldhand.main(), 0)
        self.assertFalse((self.root / "metrics").exists())
        self.assertFalse((self.root / ".cursor" / "rules" / "oldhand.mdc").exists())

    def test_display_path_renders_windows_paths_as_posix(self):
        """The JSON `path` field must not change shape on Windows.

        Exercised with PureWindowsPath so the Windows behaviour is pinned
        from any host; str() on a WindowsPath yields backslashes, which
        silently breaks consumers that compare or join these values.
        """
        root = PureWindowsPath(r"D:\a\oldhand\oldhand")
        record = root / "memory" / "lessons" / "json-creation.md"
        self.assertEqual(oldhand.display_path(root, record),
                         "memory/lessons/json-creation.md")
        outside = PureWindowsPath(r"C:\elsewhere\notes.md")
        self.assertNotIn("\\", oldhand.display_path(root, outside))

    def test_metrics_are_recorded_without_waiting_for_interpreter_exit(self):
        """Metrics must land while the process is still running.

        Deferring this to atexit made the write depend on interpreter
        finalization, which did not happen reliably on every supported
        platform and failed silently when it did not.
        """
        self.record("good")
        with mock.patch.object(sys, "argv", [str(SOURCE), "--root", str(self.root),
                                             "rebuild"]):
            self.assertEqual(oldhand.main(), 0)
        self.assertTrue((self.root / "metrics" / "daily.jsonl").exists())

    def test_metrics_are_recorded_even_when_the_command_fails(self):
        self.record("good")
        with mock.patch.object(sys, "argv", [str(SOURCE), "--root", str(self.root),
                                             "show", "no-such-record-id"]):
            self.assertNotEqual(oldhand.main(), 0)
        self.assertTrue((self.root / "metrics" / "daily.jsonl").exists())

    def test_cli_help(self):
        result = subprocess.run([sys.executable, "-B", "-m", "oldhand.cli", "--help"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("search", result.stdout)

    def test_cli_version(self):
        for flag in ("--version", "-V"):
            result = subprocess.run([sys.executable, "-B", "-m", "oldhand.cli", flag],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, f"oldhand {oldhand.OLDHAND_VERSION}\n")
            self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
