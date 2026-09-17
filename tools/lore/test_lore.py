import argparse
import ast
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import yaml


SOURCE = Path(__file__).with_name("lore.py")
spec = importlib.util.spec_from_file_location("lore_cli", SOURCE)
lore = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lore)


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
        valid, errors, _ = lore.validate_records(self.root)
        self.assertEqual([r["meta"]["id"] for r in valid], ["valid"])
        self.assertEqual(len(errors), 7)
        self.assertTrue(all("schema_version" in error for error in errors))
        self.assertEqual(lore.rebuild(self.root, quiet=True), 0)
        with contextlib.closing(lore.connect(self.root)) as con:
            self.assertEqual(con.execute("SELECT count(*) FROM entries").fetchone()[0], 1)

    def test_malformed_relations_rejected(self):
        self.record("valid")
        for index, relations in enumerate([123, [], "target", {"supersedes": 123},
                                            {"unknown": None}, {"related_to": [None]},
                                            {"related_to": [""]}]):
            self.record(f"invalid{index}", relations=relations)
        valid, errors, _ = lore.validate_records(self.root)
        self.assertEqual([r["meta"]["id"] for r in valid], ["valid"])
        self.assertEqual(len(errors), 7)
        self.assertTrue(all("relation" in error for error in errors))

    def test_duplicate_ids_reject_all_ambiguous_records(self):
        self.record("a", id="shared")
        self.record("b", id="shared")
        self.record("c", id="shared")
        self.record("valid")
        valid, errors, _ = lore.validate_records(self.root)
        self.assertEqual([r["meta"]["id"] for r in valid], ["valid"])
        self.assertTrue(all(any(f"{name}.md:" in error for error in errors)
                            for name in ("a", "b", "c")))

    def test_fingerprint_detects_same_size_edit_with_unchanged_mtime(self):
        path = self.record("a")
        os.utime(path, (1_000_000, 1_000_000))
        self.assertEqual(lore.rebuild(self.root, quiet=True), 0)
        before = lore.archive_fingerprint(self.root)
        stat = path.stat()
        path.write_text(path.read_text(encoding="utf-8").replace("Known facts.",
                                                                 "Other facts."), encoding="utf-8")
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.assertEqual(path.stat().st_size, stat.st_size)
        self.assertEqual(path.stat().st_mtime_ns, stat.st_mtime_ns)
        self.assertNotEqual(before, lore.archive_fingerprint(self.root))
        with contextlib.closing(lore.ensure_db(self.root)) as con:
            body = con.execute("SELECT body FROM entries WHERE id='a'").fetchone()[0]
            self.assertIn("Other facts.", body)
            self.assertNotIn("Known facts.", body)

    def test_fingerprint_detects_rename_without_content_or_mtime_change(self):
        path = self.record("a")
        self.assertEqual(lore.rebuild(self.root, quiet=True), 0)
        before = lore.archive_fingerprint(self.root)
        content = path.read_bytes()
        stat = path.stat()
        renamed = path.rename(path.with_name("b.md"))
        self.assertEqual(renamed.read_bytes(), content)
        self.assertEqual(renamed.stat().st_mtime_ns, stat.st_mtime_ns)
        self.assertNotEqual(before, lore.archive_fingerprint(self.root))
        with contextlib.closing(lore.ensure_db(self.root)) as con:
            self.assertEqual(con.execute("SELECT path FROM entries WHERE id='a'").fetchone()[0],
                             "memory/b.md")

    def test_current_index_is_not_rebuilt(self):
        self.record("a")
        self.assertEqual(lore.rebuild(self.root, quiet=True), 0)
        with mock.patch.object(lore, "rebuild", wraps=lore.rebuild) as rebuild:
            self.repair_cycle()
        rebuild.assert_not_called()

    def test_old_index_version_is_rebuilt_with_unchanged_markdown(self):
        self.record("a")
        self.assertEqual(lore.rebuild(self.root, quiet=True), 0)
        fingerprint = lore.archive_fingerprint(self.root)
        for key, value in (("lore_version", "0.0.0"), ("schema", "0")):
            with self.subTest(key=key):
                with contextlib.closing(lore.connect(self.root)) as con:
                    con.execute("UPDATE index_meta SET value=? WHERE key=?", (value, key))
                    con.execute("UPDATE entries SET title='stale'")
                    con.commit()
                with mock.patch.object(lore, "rebuild", wraps=lore.rebuild) as rebuild:
                    self.repair_cycle()
                rebuild.assert_called_once_with(self.root, strict=False, quiet=True)
                self.assertEqual(lore.archive_fingerprint(self.root), fingerprint)
                with contextlib.closing(lore.connect(self.root)) as con:
                    self.assertEqual(lore.read_meta(con, key), lore.LORE_VERSION if key == "lore_version" else "1")
                    self.assertEqual(con.execute("SELECT title FROM entries").fetchone()[0], "a")

    def test_empty_or_legacy_index_is_repaired(self):
        self.record("a")
        lore.rebuild(self.root, quiet=True)
        db = lore.db_path(self.root)
        with contextlib.closing(sqlite3.connect(db)) as raw:
            raw.executescript("DROP TABLE index_meta;")
            raw.commit()
        self.repair_cycle()
        for missing in ("fingerprint", "schema", "lore_version"):
            with contextlib.closing(sqlite3.connect(db)) as raw:
                raw.execute("DELETE FROM index_meta WHERE key=?", (missing,))
                raw.commit()
            self.repair_cycle()
        with contextlib.closing(sqlite3.connect(db)) as raw:
            raw.executescript("DROP TABLE entry_fts; DROP TABLE index_meta; DROP TABLE entries;")
            raw.commit()
        self.repair_cycle()

    def repair_cycle(self):
        with contextlib.closing(lore.ensure_db(self.root)) as con:
            self.assertEqual(con.execute("SELECT id FROM entries").fetchall()[0][0], "a")
            self.assertEqual(con.execute("SELECT count(*) FROM entries").fetchone()[0], 1)
            self.assertEqual(lore.read_meta(con, "schema"), "1")
            self.assertEqual(lore.read_meta(con, "lore_version"), lore.LORE_VERSION)
            self.assertEqual(lore.read_meta(con, "fingerprint"),
                             lore.archive_fingerprint(self.root))

    def test_failed_rebuild_leaves_previous_index(self):
        self.record("a")
        lore.rebuild(self.root, quiet=True)
        db = lore.db_path(self.root)
        self.record("b")
        with mock.patch.object(lore, "generate_index",
                               side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                lore.rebuild(self.root, quiet=True)
        with contextlib.closing(sqlite3.connect(db)) as raw:
            self.assertEqual(raw.execute("SELECT count(*) FROM entries").fetchone()[0], 1)
        self.assertEqual(list(db.parent.glob("*.building*")), [])
        with contextlib.closing(lore.ensure_db(self.root)) as con:
            self.assertEqual(con.execute("SELECT count(*) FROM entries").fetchone()[0], 2)

    def test_overlapping_rebuilds_use_distinct_staging_files(self):
        self.record("a")
        self.assertEqual(lore.rebuild(self.root, quiet=True), 0)
        db = lore.db_path(self.root)
        real_rebuild = lore.rebuild
        real_mkstemp = lore.tempfile.mkstemp
        staging = []

        def overlap(*args, **kwargs):
            fd, name = real_mkstemp(*args, **kwargs)
            staging.append(Path(name))
            if len(staging) == 1:
                self.assertEqual(real_rebuild(self.root, quiet=True), 0)
            return fd, name

        with mock.patch.object(lore.tempfile, "mkstemp", side_effect=overlap):
            self.assertEqual(lore.rebuild(self.root, quiet=True), 0)
        self.assertEqual(len(staging), 2)
        self.assertNotEqual(staging[0], staging[1])
        self.assertTrue(db.exists())
        self.assertEqual(list(db.parent.glob("*.building*")), [])
        self.repair_cycle()

    def test_connection_failure_cleans_staging(self):
        self.record("a")
        self.assertEqual(lore.rebuild(self.root, quiet=True), 0)
        db = lore.db_path(self.root)
        before = db.read_bytes()
        with mock.patch.object(lore.sqlite3, "connect", side_effect=sqlite3.OperationalError("boom")):
            with self.assertRaisesRegex(sqlite3.OperationalError, "boom"):
                lore.rebuild(self.root, quiet=True)
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
            rc = lore.search(self.root, query, history=False, limit=5,
                             scope=None, collection=None, log=False)
            self.assertEqual(rc, 0, query)
            self.assertIn("   id: uni\n", self.output.getvalue(), query)
            self.assertNotIn("No matching record", self.output.getvalue(), query)

    def test_search_filters_by_entry_type(self):
        self.record("lesson", type="lesson")
        self.record("decision", type="decision")
        rc = lore.search(self.root, "useful testing", history=False, limit=5,
                         scope=None, collection=None, log=False,
                         entry_type="decision")
        self.assertEqual(rc, 0)
        output = self.output.getvalue()
        self.assertIn("   id: decision\n", output)
        self.assertNotIn("   id: lesson\n", output)

    def test_search_filters_by_exact_status(self):
        self.record("current", status="current")
        self.record("resolved", status="resolved")
        rc = lore.search(self.root, "useful testing", history=False, limit=5,
                         scope=None, collection=None, log=False,
                         status="resolved")
        self.assertEqual(rc, 0)
        output = self.output.getvalue()
        self.assertIn("   id: resolved\n", output)
        self.assertNotIn("   id: current\n", output)

    def test_search_filters_by_exact_topic(self):
        self.record("backend", topics=["API Gateway"])
        self.record("frontend", topics=["interface"])
        rc = lore.search(self.root, "useful testing", history=False, limit=5,
                         scope=None, collection=None, log=False,
                         topic="api gateway")
        self.assertEqual(rc, 0)
        output = self.output.getvalue()
        self.assertIn("   id: backend\n", output)
        self.assertNotIn("   id: frontend\n", output)

    def test_search_json_is_structured_for_hits_and_misses(self):
        self.record("decision", type="decision", topics=["API Gateway"])
        rc = lore.search(self.root, "useful testing", history=False, limit=5,
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
        rc = lore.search(self.root, "term-that-does-not-exist", history=False,
                         limit=5, scope=None, collection=None, log=False,
                         json_output=True)
        self.assertEqual(rc, 0)
        payload = json.loads(self.output.getvalue())
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["searched"], 1)
        self.assertEqual(payload["results"], [])

    def test_show_json_returns_record_and_relationships(self):
        self.record("target", topics=["database"])
        self.record("source", type="decision", topics=["API Gateway"],
                    relations={"depends_on": ["target"]})
        lore.rebuild(self.root, quiet=True)
        rc = lore.show(self.root, "source", json_output=True)
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
        rc = lore.list_records(self.root, history=False, limit=10,
                               entry_type="lesson", topic="backend",
                               collection=None, json_output=False)
        self.assertEqual(rc, 0)
        output = self.output.getvalue()
        self.assertIn("active-backend", output)
        self.assertNotIn("retired-backend", output)
        self.assertNotIn("active-frontend", output)

        self.output.seek(0)
        self.output.truncate()
        rc = lore.list_records(self.root, history=True, limit=1,
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
        rc = lore.list_records(self.root, history=False, limit=10,
                               entry_type=None, topic=None, collection=None,
                               json_output=True, status="deprecated")
        self.assertEqual(rc, 0)
        payload = json.loads(self.output.getvalue())
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["records"][0]["id"], "retired")
        self.assertEqual(payload["filters"]["status"], "deprecated")

    def test_topics_lists_active_topic_counts_as_json(self):
        self.record("one", topics=["Backend", "testing"])
        self.record("two", topics=["Backend"])
        self.record("old", status="deprecated", topics=["retired-only"])
        rc = lore.list_topics(self.root, limit=1, collection=None, json_output=True)
        self.assertEqual(rc, 0)
        payload = json.loads(self.output.getvalue())
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["returned"], 1)
        self.assertEqual(payload["topics"][0]["key"], "backend")
        self.assertEqual(payload["topics"][0]["record_count"], 2)

    def test_collections_reports_record_and_topic_counts(self):
        self.record("active", topics=["backend", "testing"])
        self.record("old", status="deprecated", topics=["legacy"])
        rc = lore.list_collections(self.root, json_output=True)
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
        self.assertEqual(lore.relate(self.root, "source", "depends_on", "target"), 0)
        meta = yaml.safe_load(source.read_text(encoding="utf-8").split("---\n")[1])
        self.assertEqual(meta["relations"], {"depends_on": ["target"]})
        self.assertNotEqual(str(meta["updated_at"]), "2026-09-17 00:00:00+00:00")

        self.assertEqual(lore.relate(self.root, "source", "depends_on", "target"), 0)
        meta = yaml.safe_load(source.read_text(encoding="utf-8").split("---\n")[1])
        self.assertEqual(meta["relations"], {"depends_on": ["target"]})

    def test_relate_rejects_unknown_and_self_targets(self):
        source = self.record("source")
        before = source.read_bytes()
        self.assertEqual(lore.relate(self.root, "source", "depends_on", "missing"), 1)
        self.assertEqual(lore.relate(self.root, "source", "depends_on", "source"), 1)
        self.assertEqual(source.read_bytes(), before)

    def test_unrelate_removes_relationship_and_rejects_missing(self):
        source = self.record("source", relations={"depends_on": ["target"]})
        self.record("target")
        self.assertEqual(lore.unrelate(self.root, "source", "depends_on", "target"), 0)
        meta = yaml.safe_load(source.read_text(encoding="utf-8").split("---\n")[1])
        self.assertEqual(meta["relations"], {})
        after = source.read_bytes()
        self.assertEqual(lore.unrelate(self.root, "source", "depends_on", "target"), 1)
        self.assertEqual(source.read_bytes(), after)

    def test_supersede_updates_both_records_atomically(self):
        old = self.record("old")
        new = self.record("new")
        self.assertEqual(lore.supersede_record(self.root, "old", "new"), 0)
        old_meta = yaml.safe_load(old.read_text(encoding="utf-8").split("---\n")[1])
        new_meta = yaml.safe_load(new.read_text(encoding="utf-8").split("---\n")[1])
        self.assertEqual(old_meta["status"], "superseded")
        self.assertEqual(new_meta["relations"], {"supersedes": ["old"]})
        valid, errors, _ = lore.validate_records(self.root)
        self.assertEqual(len(valid), 2)
        self.assertEqual(errors, [])

    def test_supersede_unknown_id_changes_nothing(self):
        old = self.record("old")
        before = old.read_bytes()
        self.assertEqual(lore.supersede_record(self.root, "old", "missing"), 1)
        self.assertEqual(old.read_bytes(), before)

    def test_new_record_topics_round_trip(self):
        args = argparse.Namespace(
            title="A topic test", type="lesson", importance="normal",
            topics="on, null, api: gateway, *backend, café",
            status="current", scope="subsystem", risk="low",
            durability="situational", evidence="documented",
            summary=None, knowledge=None, verification=None, collection=None)
        rc = lore.new_record(self.root, args)
        self.assertEqual(rc, 0)
        path = self.root / "memory" / "lessons" / "a-topic-test.md"
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count("topics:"), 1, text)
        meta = yaml.safe_load(text.split("---\n")[1])
        self.assertEqual(meta["topics"],
                         ["on", "null", "api: gateway", "*backend", "café"])
        valid, errors, _ = lore.validate_records(self.root)
        self.assertEqual(len(valid), 1)
        self.assertEqual(errors, [])

    def test_new_record_json_output(self):
        args = argparse.Namespace(
            title="JSON creation", type="lesson", importance="normal",
            topics="automation", status="current", scope="subsystem", risk="low",
            durability="situational", evidence="documented", summary=None,
            knowledge=None, verification=None, collection=None,
            json_output=True, dry_run=False)
        rc = lore.new_record(self.root, args)
        self.assertEqual(rc, 0)
        payload = json.loads(self.output.getvalue())
        self.assertTrue(payload["created"])
        self.assertFalse(payload["dry_run"])
        self.assertEqual(payload["id"], "lore_json_creation")
        self.assertEqual(payload["path"], "memory/lessons/json-creation.md")

    def test_new_record_dry_run_writes_nothing(self):
        args = argparse.Namespace(
            title="Preview only", type="lesson", importance="normal",
            topics="automation", status="current", scope="subsystem", risk="low",
            durability="situational", evidence="documented", summary="Preview summary.",
            knowledge="Preview knowledge.", verification="Preview verification.",
            collection=None, json_output=False, dry_run=True)
        rc = lore.new_record(self.root, args)
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
                if child.name in (".lore", "metrics"):
                    continue
                if child.is_file():
                    child.unlink()
                else:
                    import shutil
                    shutil.rmtree(child)
            if seed:
                self.record("retired-one", status="superseded")
            rc = lore.metrics(self.root, full=True, export=None)
            self.assertEqual(rc, 0, self.errors.getvalue())
            self.assertIn("findability", self.output.getvalue())
            self.assertIn("N/A", self.output.getvalue())
            self.assertNotIn("Traceback", self.output.getvalue())
            self.assertNotIn("TypeError", self.output.getvalue())

    def test_selftest(self):
        self.assertEqual(lore.selftest(), 0)

    def test_cli_help(self):
        result = subprocess.run([sys.executable, "-B", str(SOURCE), "--help"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("search", result.stdout)


if __name__ == "__main__":
    unittest.main()
