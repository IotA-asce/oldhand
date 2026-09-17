import contextlib
from datetime import datetime
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import from_claude_memory
import from_markdown
import from_repo_memory
import resync


class MigrationTestCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.archive = self.root / "archive"
        self.archive.mkdir()

    def invoke(self, module, *args):
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        with mock.patch.object(sys, "argv", [module.__file__, *map(str, args)]):
            with contextlib.redirect_stdout(self.stdout), contextlib.redirect_stderr(self.stderr):
                return module.main()


class MarkdownFrontmatterTests(MigrationTestCase):
    def test_block_scalar_summaries(self):
        for marker, expected in (("|", "First line.\nSecond line.\n"),
                                 (">", "First line. Second line.\n"),
                                 ("|-", "First line.\nSecond line."),
                                 (">-", "First line. Second line.")):
            with self.subTest(marker=marker):
                fields, body = from_markdown.parse_frontmatter(
                    f"---\nSummary: {marker}\n  First line.\n  Second line.\n---\nBody\n")
                self.assertEqual(fields["summary"], expected)
                self.assertEqual(body, "Body\n")

    def test_yaml_lists_quotes_and_comments(self):
        fields, body = from_markdown.parse_frontmatter(
            '---\ntitle: "A: title # literal"\ntags: ["one, two", three]\n'
            'description: "Quoted \\"words\\"" # ignored\n---\nBody\n')
        self.assertEqual(fields["title"], "A: title # literal")
        self.assertEqual(fields["tags"], ["one, two", "three"])
        self.assertEqual(fields["description"], 'Quoted "words"')
        self.assertEqual(body, "Body\n")

    def test_non_mapping_or_invalid_frontmatter_preserves_source(self):
        for header in ("[one, two]", "summary: [unterminated"):
            with self.subTest(header=header):
                text = f"---\n{header}\n---\nBody\n"
                self.assertEqual(from_markdown.parse_frontmatter(text), ({}, text))

    def test_migrated_summary_uses_block_scalar(self):
        source = self.source / "note.md"
        raw = "---\nsummary: >-\n  Useful first line.\n  Useful second line.\n---\n# Note\n\nOther prose.\n"
        source.write_text(raw, encoding="utf-8")
        self.assertEqual(self.invoke(from_markdown, self.source, self.archive), 0)
        records = list((self.archive / "memory").rglob("*.md"))
        self.assertEqual(len(records), 1)
        self.assertIn("## Summary\n\nUseful first line. Useful second line.\n", records[0].read_text())
        self.assertEqual(source.read_text(), raw)


class ClaudeMemoryFrontmatterTests(MigrationTestCase):
    def parse(self, text):
        return from_claude_memory.parse_source(text)

    def test_delimiters_must_be_full_lines(self):
        fields, body = self.parse(
            "---\nname: beta-record\ndescription: Second record.\n---\nBody text.\n")
        self.assertEqual(fields, {"name": "beta-record", "description": "Second record."})
        self.assertEqual(body, "Body text.")

    def test_embedded_dashes_and_indented_delimiter_are_yaml_content(self):
        fields, body = self.parse(
            '--- \r\nname: dash-note\r\ndescription: |-\r\n  A---B\r\n'
            '  ---\r\n  Last line.\r\nmetadata:\r\n  type: project\r\n---\r\nBody\r\n')
        self.assertEqual(fields["description"], "A---B\n---\nLast line.")
        self.assertEqual(fields["type"], "project")
        self.assertEqual(body, "Body")
        fields, body = self.parse('---\ndescription: "A---B" # comment\n---')
        self.assertEqual(fields["description"], "A---B")
        self.assertEqual(body, "")

    def test_invalid_or_missing_delimiters_preserve_text(self):
        for text in ("---not a delimiter\nname: wrong\n---\nBody",
                     "---\nname: incomplete", "---\nname: [invalid\n---\nBody",
                     "---\n[one, two]\n---\nBody"):
            with self.subTest(text=text):
                self.assertEqual(self.parse(text), ({}, text))

    def test_divider_inside_body_does_not_end_frontmatter(self):
        fields, body = self.parse(
            "---\nname: divider-record\n---\nBefore\n\n---\n\nAfter\n")
        self.assertEqual(fields, {"name": "divider-record"})
        self.assertEqual(body, "Before\n\n---\n\nAfter")

    def test_yaml_values_and_nested_metadata_survive(self):
        fields, body = self.parse(
            '---\nname: "quoted-name"\ndescription: "Hook: with colon"\n'
            "modified: 2026-02-03T04:05:06+00:00\ntype: reference\nmetadata:\n"
            "  type: project\n  source: int\n---\nBody\n")
        self.assertEqual(fields["name"], "quoted-name")
        self.assertEqual(fields["description"], "Hook: with colon")
        self.assertEqual(fields["modified"], datetime.fromisoformat("2026-02-03T04:05:06+00:00"))
        self.assertEqual(fields["type"], "reference")
        self.assertEqual(fields["metadata"], {"type": "project", "source": "int"})
        self.assertEqual(body, "Body")

    def test_yaml_scalar_names_preserve_legacy_identity(self):
        for name in ("on", "001", "null", "1.20"):
            with self.subTest(name=name):
                source = self.source / "note.md"
                source.write_text(f"---\nname: {name}\ndescription: Note\n---\nBody\n",
                                  encoding="utf-8")
                fields, _ = self.parse(source.read_text())
                self.assertEqual(fields["name"], name)
                self.assertEqual(self.invoke(from_claude_memory, self.source, self.archive), 0)
                output = self.archive / "memory" / "lessons" / f"{name}.md"
                self.assertTrue(output.is_file())
                fields, _ = from_markdown.parse_frontmatter(output.read_text())
                self.assertEqual(fields["id"], f"lore_{name}")

    def test_cli_migration_preserves_source_and_is_repeatable(self):
        source = self.source / "on.md"
        raw = "---\nname: on\ndescription: Useful note\ntype: [project]\n---\nBody\n"
        source.write_text(raw, encoding="utf-8")
        command = [sys.executable, from_claude_memory.__file__,
                   str(self.source), str(self.archive)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = self.archive / "memory" / "lessons" / "on.md"
        first = output.read_bytes()
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.read_bytes(), first)
        self.assertEqual(source.read_text(), raw)
        fields, _ = from_markdown.parse_frontmatter(first.decode())
        self.assertEqual(fields["id"], "lore_on")

    def test_migrated_record_keeps_yaml_description_and_timestamp(self):
        (self.source / "yaml-record.md").write_text(
            "---\nname: yaml-record\n"
            'description: "Keeps: colon"\nmodified: 2026-02-03T04:05:06+00:00\n---\n'
            "Body mentions [[yaml-record]].\n",
            encoding="utf-8")
        self.assertEqual(self.invoke(from_claude_memory, self.source, self.archive), 0)
        records = list((self.archive / "memory").rglob("*.md"))
        self.assertEqual(len(records), 1)
        record = records[0].read_text()
        self.assertIn("Keeps: colon", record)
        self.assertEqual(records[0].stem, "yaml-record")
        fields, _ = from_markdown.parse_frontmatter(record)
        self.assertEqual(fields["created_at"], datetime.fromisoformat("2026-02-03T04:05:06+00:00"))


class ClaudeMemoryStatusTests(MigrationTestCase):
    def test_negative_resolution_is_current(self):
        for description in ("UNRESOLVED: waiting on evidence", "Still unresolved",
                            "not resolved", "NOT RESOLVED: retry needed",
                            "Not\nresolved yet", "Resolvedness is unknown",
                            "UNRESOLVED: cannot be resolved yet"):
            with self.subTest(description=description):
                self.assertEqual(from_claude_memory.pick_status(description), "current")

    def test_positive_resolution_and_supersession(self):
        for description, expected in (("RESOLVED: confirmed", "resolved"),
                                      ("Issue resolved yesterday", "resolved"),
                                      ("SUPERSEDED: not resolved", "superseded"),
                                      ("A " * 31 + "RESOLVED", "current"),
                                      ("Ongoing investigation", "current")):
            with self.subTest(description=description):
                self.assertEqual(from_claude_memory.pick_status(description), expected)

    def test_migrated_unresolved_record_stays_current(self):
        (self.source / "open.md").write_text(
            "---\nname: open\ndescription: 'UNRESOLVED: needs investigation'\n---\nDetails\n",
            encoding="utf-8")
        self.assertEqual(self.invoke(from_claude_memory, self.source, self.archive), 0)
        record = next((self.archive / "memory").rglob("*.md"))
        fields, _ = from_markdown.parse_frontmatter(record.read_text())
        self.assertEqual(fields["status"], "current")


class RepoMemoryIdentityTests(MigrationTestCase):
    def entry(self, relative, title):
        directory = self.source / relative
        directory.mkdir(parents=True)
        (directory / "SUMMARY.md").write_text(f"# {title}\n\nFinding about {title}.\n", encoding="utf-8")
        return directory

    def migrate(self):
        self.assertEqual(self.invoke(from_repo_memory, self.source, self.archive / "svc", "svc"), 0)
        records = {}
        for path in (self.archive / "svc" / "memory").rglob("*.md"):
            fields, body = from_markdown.parse_frontmatter(path.read_text())
            title = body.lstrip().splitlines()[0]
            records[title] = (fields["id"], path.relative_to(self.archive), path.read_bytes())
        return records

    def test_repeated_dated_names_do_not_overwrite(self):
        self.entry("fixes/2026-01-01-retry", "First retry")
        self.entry("fixes/2026-02-01-retry", "Second retry")
        records = self.migrate()
        self.assertEqual(len(records), 2)
        self.assertEqual(len({record[0] for record in records.values()}), 2)
        self.assertEqual(records, self.migrate())

    def test_category_and_normalized_suffix_collisions(self):
        for relative, title in (("fixes/2026-01-01-retry", "Fix"),
                                ("features/2026-01-01-retry", "Feature"),
                                ("other/fixes/2026-01-01-retry", "Nested"),
                                ("fixes/2026-02-01-retry-fixes", "Suffix"),
                                ("fixes/2026-03-01-retry_fixes", "Normalized")):
            self.entry(relative, title)
        records = self.migrate()
        self.assertEqual(len(records), 5)
        self.assertEqual(len({record[0] for record in records.values()}), 5)
        self.assertEqual(records, self.migrate())

    def test_new_earlier_collision_keeps_existing_identity_and_relations(self):
        self.entry("fixes/2026-02-01-retry", "Original")
        before = self.migrate()["# Original"]
        self.assertEqual(before[0], "lore_svc_retry")
        self.assertEqual(before[1].as_posix(), "svc/memory/fixes/retry.md")
        (self.archive / "reconcile.jsonl").write_text(json.dumps({
            "id": before[0], "status": "superseded",
            "relations": {"related_to": ["lore_svc_other"]}}) + "\n", encoding="utf-8")
        self.entry("features/2026-01-01-retry", "Earlier")
        records = self.migrate()
        self.assertEqual(records["# Original"][:2], before[:2])
        self.assertNotEqual(records["# Earlier"][0], before[0])
        fields, _ = from_markdown.parse_frontmatter(records["# Original"][2].decode())
        self.assertEqual(fields["status"], "superseded")
        self.assertEqual(fields["relations"], {"related_to": ["lore_svc_other"]})

    def test_historical_duplicate_ids_keep_paths_and_become_unique(self):
        for category in ("features", "fixes"):
            self.entry(f"{category}/2026-01-01-retry", category)
            output = self.archive / "svc" / "memory" / category / "retry.md"
            output.parent.mkdir(parents=True)
            output.write_text(
                f"---\nid: lore_svc_retry\n---\n# {category}\n\n"
                f"Source entry: `{category}/2026-01-01-retry`\n", encoding="utf-8")
        records = self.migrate()
        self.assertEqual(len({record[0] for record in records.values()}), 2)
        self.assertEqual(records["# features"][0], "lore_svc_retry")
        for record in records.values():
            self.assertEqual(record[1].name, "retry.md")
        self.assertEqual(records, self.migrate())

    def test_legacy_links_and_unrelated_destination_are_preserved(self):
        directory = self.entry("fixes/2026-01-01-retry", "Original")
        (directory / "LINKS.md").write_text("[Source](../other/SUMMARY.md)\n", encoding="utf-8")
        output = self.archive / "svc" / "memory" / "fixes" / "retry.md"
        output.parent.mkdir(parents=True)
        output.write_text("---\nid: lore_svc_retry\n---\n# Original\n\nOld links\n", encoding="utf-8")
        unrelated = output.with_name("other.md")
        unrelated.write_text("---\nid: manual\n---\n# Unrelated\n", encoding="utf-8")
        raw = unrelated.read_bytes()
        records = self.migrate()
        self.assertEqual(records["# Original"][:2], ("lore_svc_retry", output.relative_to(self.archive)))
        self.assertIn(b"[Source](../other/SUMMARY.md)", records["# Original"][2])
        self.assertIn(b"Source entry: `fixes/2026-01-01-retry`", records["# Original"][2])
        self.entry("fixes/2026-01-01-other", "New other")
        self.migrate()
        self.assertEqual(unrelated.read_bytes(), raw)
        self.assertEqual((directory / "LINKS.md").read_text(), "[Source](../other/SUMMARY.md)\n")

    def test_quoted_legacy_id_keeps_identity_and_overrides(self):
        self.entry("fixes/2026-01-01-retry", "Original")
        output = self.archive / "svc" / "memory" / "fixes" / "retry.md"
        output.parent.mkdir(parents=True)
        output.write_text(
            '---\nid: "lore_svc_retry" # stable identity\n---\n# Original\n\nOld links\n',
            encoding="utf-8")
        (self.archive / "reconcile.jsonl").write_text(json.dumps({
            "id": "lore_svc_retry", "status": "superseded"}) + "\n", encoding="utf-8")
        records = self.migrate()
        self.assertEqual(len(records), 1)
        self.assertEqual(records["# Original"][:2],
                         ("lore_svc_retry", output.relative_to(self.archive)))
        fields, _ = from_markdown.parse_frontmatter(records["# Original"][2].decode())
        self.assertEqual(fields["status"], "superseded")
        self.assertEqual(records, self.migrate())

    def test_source_reference_in_links_does_not_steal_identity(self):
        self.entry("fixes/2026-01-01-retry", "Original")
        directory = self.entry("fixes/2026-02-01-retry", "Other")
        (directory / "LINKS.md").write_text(
            "Source entry: `fixes/2026-01-01-retry`\n", encoding="utf-8")
        before = self.migrate()
        self.assertEqual(before, self.migrate())

    def test_historical_overwritten_record_keeps_legacy_id(self):
        self.entry("fixes/2026-01-01-retry", "First")
        self.entry("fixes/2026-02-01-retry", "Last")
        output = self.archive / "svc" / "memory" / "fixes" / "retry.md"
        output.parent.mkdir(parents=True)
        output.write_text(
            "---\nid: lore_svc_retry\n---\n\n# Last\n\n## References\n\n"
            "Source entry: `fixes/2026-02-01-retry`\n", encoding="utf-8")
        records = self.migrate()
        self.assertEqual(len(records), 2)
        self.assertEqual(records["# Last"][0], "lore_svc_retry")
        self.assertEqual(records["# Last"][1], output.relative_to(self.archive))
        self.assertNotEqual(records["# First"][0], "lore_svc_retry")


class ResyncTests(MigrationTestCase):
    def setUp(self):
        super().setUp()
        (self.archive / "sources.jsonl").write_text("", encoding="utf-8")

    def test_rebuild_failure_is_not_hidden_by_successful_validation(self):
        results = [subprocess.CompletedProcess([], 7, "", "rebuild failed\n"),
                   subprocess.CompletedProcess([], 0, "validation passed\n", "")]
        with mock.patch.object(resync.subprocess, "run", side_effect=results) as run:
            self.assertEqual(self.invoke(resync, self.archive), 1)
        self.assertEqual([call.args[0][-1] for call in run.call_args_list], ["rebuild", "validate"])
        self.assertIn("rebuild failed", self.stdout.getvalue())

    def test_empty_output_and_exit_codes(self):
        for rebuild_code, validate_code in ((0, 0), (1, 0), (0, 1), (1, 1)):
            for output in ("", " \n\t\n"):
                with self.subTest(rebuild=rebuild_code, validate=validate_code, output=output):
                    results = [subprocess.CompletedProcess([], rebuild_code, output, ""),
                               subprocess.CompletedProcess([], validate_code, output, "")]
                    with mock.patch.object(resync.subprocess, "run", side_effect=results):
                        self.assertEqual(self.invoke(resync, self.archive),
                                         int(bool(rebuild_code or validate_code)))
                    self.assertIn("rebuild", self.stdout.getvalue())
                    self.assertIn("validate", self.stdout.getvalue())

    def test_whitespace_stdout_does_not_hide_stderr(self):
        results = [subprocess.CompletedProcess([], 1, " \n", "useful rebuild error\n"),
                   subprocess.CompletedProcess([], 0, " \n", "validation passed\n")]
        with mock.patch.object(resync.subprocess, "run", side_effect=results):
            self.assertEqual(self.invoke(resync, self.archive), 1)
        self.assertIn("useful rebuild error", self.stdout.getvalue())
        self.assertIn("validation passed", self.stdout.getvalue())

    def test_source_failure_still_propagates(self):
        (self.archive / "sources.jsonl").write_text(json.dumps({
            "tool": "repo_memory", "src": str(self.source), "collection": "svc"}) + "\n",
            encoding="utf-8")
        results = [subprocess.CompletedProcess([], 2, "", "migration failed\n"),
                   subprocess.CompletedProcess([], 0, "rebuilt\n", ""),
                   subprocess.CompletedProcess([], 0, "validated\n", "")]
        with mock.patch.object(resync.subprocess, "run", side_effect=results):
            self.assertEqual(self.invoke(resync, self.archive), 1)
        self.assertIn("1 source(s) did not sync", self.stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
