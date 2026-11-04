import contextlib
import io
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock
from urllib.parse import unquote

import yaml

from oldhand import cli, indexing
from oldhand.records import parse_record


class ObsidianTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.output = io.StringIO()
        self.errors = io.StringIO()
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(contextlib.redirect_stdout(self.output))
        stack.enter_context(contextlib.redirect_stderr(self.errors))

    def record(self, rid, path=None, **changes):
        meta = dict(schema_version=1, id=rid, type="lesson", status="current",
                    importance="normal", scope="repository", risk="low",
                    durability="long_lived", evidence="verified", topics=["testing"],
                    created_at="2026-09-17T00:00:00+00:00",
                    updated_at="2026-09-17T00:00:00+00:00", relations={})
        meta.update(changes)
        target = self.root / (path or f"memory/{rid}.md")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("---\n" + yaml.safe_dump(meta, sort_keys=False) +
                          f"---\n\n# {rid}\n\n## Summary\n\nSynthetic finding about retries."
                          "\n\n## Knowledge\n\nPreserve this authored text.\n",
                          encoding="utf-8")
        return target

    def links(self, path):
        text = path.read_text(encoding="utf-8")
        return [(path.parent / unquote(link)).resolve()
                for link in re.findall(r"\]\(([^)]+)\)", text)]

    def hubs(self):
        return sorted((self.root / "_topics").glob("*.md"))

    def test_original_records_link_to_relations_and_topics(self):
        target = self.record("target")
        source = self.record("source", relations={"depends_on": ["target"]})
        before = parse_record(source)
        self.assertEqual(cli.obsidian(self.root), 0)
        self.assertIn(target, self.links(source))
        self.assertIn("**depends_on**", source.read_text())
        self.assertIn(self.hubs()[0], self.links(source))
        after = parse_record(source)
        self.assertEqual(after["meta"], before["meta"])
        self.assertEqual(after["body"], before["body"])
        self.assertIn(source, self.links(self.hubs()[0]))

    def test_cross_collection_links_resolve_duplicate_basenames(self):
        source = self.record("source", "alpha/memory/shared.md",
                             relations={"related_to": ["target"]})
        target = self.record("target", "beta/memory/shared.md")
        self.assertEqual(cli.obsidian(self.root), 0)
        self.assertIn(target, self.links(source))
        self.assertEqual(set(self.links(self.hubs()[0])), {source, target})
        self.assertIn("alpha", (self.root / "HOME.md").read_text())

    def test_paths_and_topic_names_are_safe_and_encoded(self):
        source = self.record("source", "memory/认证 [one] # (two)%.md",
                             topics=["../outside", "API/Gateway", "认证", "A", "a"])
        self.assertEqual(cli.obsidian(self.root), 0)
        self.assertEqual(len(self.hubs()), 4)
        self.assertEqual(len({p.name.casefold() for p in self.hubs()}), 4)
        for hub in self.hubs():
            self.assertIn(source, self.links(hub))
            self.assertIn("%23", hub.read_text())
        self.assertFalse((self.root / "outside.md").exists())

    def test_refresh_is_idempotent_and_preserves_authored_bytes(self):
        source = self.record("source")
        original = source.read_bytes().replace(b"\n", b"\r\n")
        source.write_bytes(original)
        self.assertEqual(cli.obsidian(self.root), 0)
        self.assertTrue(source.read_bytes().startswith(original))
        first = source.read_bytes()
        stat = source.stat()
        self.assertEqual(cli.obsidian(self.root), 0)
        self.assertEqual(source.read_bytes(), first)
        self.assertEqual(source.stat().st_mtime_ns, stat.st_mtime_ns)

    def test_user_text_after_generated_section_is_preserved(self):
        source = self.record("source")
        self.assertEqual(cli.obsidian(self.root), 0)
        source.write_bytes(source.read_bytes() + b"\n## My notes\n\nKeep me.\n")
        self.assertEqual(cli.obsidian(self.root), 0)
        self.assertTrue(source.read_bytes().endswith(b"\n## My notes\n\nKeep me.\n"))
        self.assertIn("Keep me.", parse_record(source)["body"])

    def test_rebuild_refreshes_links_and_removes_only_owned_stale_hubs(self):
        source = self.record("source", topics=["old-topic"])
        self.assertEqual(cli.obsidian(self.root), 0)
        old_hub = self.hubs()[0]
        personal = self.root / "_topics/personal.md"
        personal.write_text("# Personal notes\n")
        meta = dict(parse_record(source)["meta"])
        meta["topics"] = ["new-topic"]
        meta["relations"] = {"related_to": ["target"]}
        body = parse_record(source)["body"]
        source.write_text("---\n" + yaml.safe_dump(meta) + "---\n\n" + body + "\n")
        target = self.record("target", topics=["new-topic"])
        self.assertEqual(indexing.rebuild(self.root, quiet=True), 0)
        self.assertIn(target, self.links(source))
        self.assertFalse(old_hub.exists())
        self.assertEqual(personal.read_text(), "# Personal notes\n")
        self.assertNotIn(old_hub, self.links(source))

    def test_no_graph_writes_until_explicit_opt_in(self):
        source = self.record("source")
        before = source.read_bytes()
        self.assertEqual(indexing.rebuild(self.root, quiet=True), 0)
        self.assertEqual(source.read_bytes(), before)
        self.assertFalse((self.root / "_topics").exists())

    def test_opt_in_survives_deleting_derived_index(self):
        import shutil
        self.record("first")
        self.assertEqual(cli.obsidian(self.root), 0)
        shutil.rmtree(self.root / ".oldhand")
        second = self.record("second")
        self.assertEqual(indexing.rebuild(self.root, quiet=True), 0)
        self.assertIn(self.hubs()[0], self.links(second))

    def test_generated_links_do_not_pollute_retrieval_or_fingerprint(self):
        source = self.record("source", topics=[])
        self.record("QuasarTarget", topics=[])
        self.assertEqual(cli.obsidian(self.root), 0)
        self.assertEqual(cli.relate(self.root, "source", "depends_on", "QuasarTarget"), 0)
        self.assertIn("QuasarTarget", source.read_text())
        with contextlib.closing(indexing.ensure_db(self.root)) as con:
            body = con.execute("SELECT body FROM entries WHERE id='source'").fetchone()[0]
            self.assertNotIn("QuasarTarget", body)
            self.assertNotIn("Obsidian", body)
            matches = con.execute("SELECT entry_id FROM entry_fts WHERE entry_fts MATCH ?",
                                  ('"QuasarTarget"',)).fetchall()
            self.assertEqual({row[0] for row in matches}, {"QuasarTarget"})
            self.assertEqual(indexing.read_meta(con, "fingerprint"),
                             indexing.archive_fingerprint(self.root))

    def test_refuses_existing_user_home_before_changing_records(self):
        source = self.record("source")
        before = source.read_bytes()
        home = self.root / "HOME.md"
        home.write_text("# My dashboard\n")
        self.assertEqual(cli.obsidian(self.root), 1)
        self.assertEqual(home.read_text(), "# My dashboard\n")
        self.assertEqual(source.read_bytes(), before)
        self.assertFalse((self.root / "_topics").exists())

    def test_existing_user_topic_files_are_preserved(self):
        self.record("source")
        folder = self.root / "_topics"
        folder.mkdir()
        personal = folder / "testing.md"
        personal.write_text("# My topic notes\n")
        self.assertEqual(cli.obsidian(self.root), 0)
        self.assertEqual(personal.read_text(), "# My topic notes\n")

    def test_replaces_legacy_home_but_preserves_legacy_topic_notes(self):
        self.record("source")
        (self.root / "HOME.md").write_text(
            "# Oldhand\n\nGenerated by `oldhand obsidian`. Edits here are overwritten.\n"
            "Canonical records live under each collection's `memory/`.")
        self.assertEqual(cli.obsidian(self.root), 0)
        self.assertIn("Graph", (self.root / "HOME.md").read_text())

    def test_symlinked_output_and_records_cannot_escape_root(self):
        for kind in ("topics", "record"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as outside:
                root = self.root / kind
                root.mkdir()
                source = self.record(kind, f"{kind}/memory/source.md")
                external = Path(outside) / "source.md"
                if kind == "topics":
                    (root / "_topics").symlink_to(outside, target_is_directory=True)
                else:
                    external.write_bytes(source.read_bytes())
                    source.unlink()
                    source.symlink_to(external)
                before = external.read_bytes() if external.exists() else None
                self.assertEqual(cli.obsidian(root), 1)
                self.assertFalse((root / "HOME.md").exists())
                if before is not None:
                    self.assertEqual(external.read_bytes(), before)

    def test_empty_archive_can_enable_sync_for_future_records(self):
        self.assertEqual(cli.obsidian(self.root), 0)
        source = self.record("later")
        self.assertEqual(indexing.rebuild(self.root, quiet=True), 0)
        self.assertIn(self.hubs()[0], self.links(source))

    def test_write_failure_rolls_back_records_and_generated_files(self):
        from oldhand import obsidian
        source = self.record("source")
        before = source.read_bytes()
        original_write = obsidian._atomic_write

        def fail_on_home(path, data):
            if path == self.root / "HOME.md":
                raise OSError("simulated disk failure")
            original_write(path, data)

        with mock.patch.object(obsidian, "_atomic_write", side_effect=fail_on_home):
            self.assertEqual(cli.obsidian(self.root), 1)
        self.assertEqual(source.read_bytes(), before)
        self.assertFalse((self.root / "HOME.md").exists())
        self.assertFalse((self.root / "_topics/.oldhand.json").exists())
        self.assertEqual(self.hubs(), [])

    def test_conflicting_user_hub_is_not_overwritten(self):
        self.record("source")
        self.assertEqual(cli.obsidian(self.root), 0)
        hub = self.hubs()[0]
        hub.write_text("# A user replaced this note\n")
        source = self.record("another")
        before = source.read_bytes()
        self.assertEqual(cli.obsidian(self.root), 1)
        self.assertEqual(hub.read_text(), "# A user replaced this note\n")
        self.assertEqual(source.read_bytes(), before)

    def test_topic_slug_collisions_keep_distinct_hubs(self):
        self.record("source", topics=["a?", "a!", "认证", "認証"])
        self.assertEqual(cli.obsidian(self.root), 0)
        self.assertEqual(len(self.hubs()), 4)
        self.assertEqual(len({path.name for path in self.hubs()}), 4)

    def test_invalid_archive_is_not_modified_by_explicit_sync(self):
        source = self.record("source", relations={"depends_on": ["missing"]})
        before = source.read_bytes()
        self.assertEqual(cli.obsidian(self.root), 1)
        self.assertEqual(source.read_bytes(), before)
        self.assertFalse((self.root / "HOME.md").exists())

    def test_graph_failure_warns_but_rebuild_still_indexes_valid_records(self):
        self.record("first")
        self.assertEqual(cli.obsidian(self.root), 0)
        (self.root / "HOME.md").write_text("# User replaced dashboard\n")
        self.record("second")
        self.assertEqual(indexing.rebuild(self.root, quiet=True), 0)
        self.assertIn("Obsidian", self.errors.getvalue())
        with contextlib.closing(indexing.ensure_db(self.root)) as con:
            self.assertEqual(con.execute("SELECT count(*) FROM entries").fetchone()[0], 2)

    def test_malformed_graph_markers_do_not_hide_authored_knowledge(self):
        source = self.record("source")
        source.write_text(source.read_text() + "\n<!-- oldhand:graph:start -->\nKeep this.\n")
        self.assertEqual(cli.obsidian(self.root), 1)
        self.assertIn("Keep this.", source.read_text())
        self.assertIn("graph", self.errors.getvalue().lower())


if __name__ == "__main__":
    unittest.main()
