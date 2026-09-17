import contextlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

import yaml

REPO = Path(__file__).resolve().parent
LORE_PY = REPO / "lore" / "lore.py"
INSTALL_PY = REPO / "install.py"


class E2ETestCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.archive = self.root / "archive"
        (self.archive / "memory").mkdir(parents=True)
        self.env = {k: v for k, v in os.environ.items() if k != "LORE_ROOT"}
        self.env["HOME"] = str(self.root / "home")
        Path(self.env["HOME"]).mkdir()
        self.env["PATH"] = "/usr/bin:/bin"
        self.env["SHELL"] = "/bin/zsh"
        self.env["USERPROFILE"] = self.env["HOME"]
        self.env["PYTHONDONTWRITEBYTECODE"] = "1"

    def lore(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(LORE_PY), "--root", str(self.archive), *args],
            capture_output=True, text=True, env=self.env)

    def record(self, name, **changes):
        meta = dict(schema_version=1, id=name, type="lesson", status="current",
                    importance="normal", scope="repository", risk="low",
                    durability="long_lived", evidence="verified", topics=["testing"],
                    created_at="2026-09-17T00:00:00+00:00",
                    updated_at="2026-09-17T00:00:00+00:00", relations={})
        meta.update(changes)
        path = self.archive / "memory" / f"{name}.md"
        path.write_text("---\n" + yaml.safe_dump(meta) + "---\n\n# " + name +
                        "\n\n## Summary\n\n" + name + " summary about database retries.\n\n"
                        "## Knowledge\n\n" + name + " knowledge: the gateway retries and 认证.\n",
                        encoding="utf-8")
        return path


class CoreCliTests(E2ETestCase):
    def test_validation_rejects_and_rebuild_fails_open(self):
        self.record("good")
        bad_version = self.record("badver", schema_version="v1")
        bad_relation = self.record("badrel", relations={"supersedes": 123})
        result = self.lore("validate")
        self.assertEqual(result.returncode, 1)
        for path in (bad_version, bad_relation):
            self.assertIn(path.name, result.stdout)
        result = self.lore("rebuild")
        self.assertEqual(result.returncode, 0)
        result = self.lore("search", "database")
        self.assertIn("good", result.stdout)
        self.assertNotIn("badver", result.stdout)
        self.assertNotIn("badrel", result.stdout)

    def test_unicode_query_finds_record(self):
        self.record("good")
        self.lore("rebuild")
        result = self.lore("search", "认证")
        self.assertIn("id: good", result.stdout)

    def test_same_second_edit_and_rename_are_reindexed(self):
        path = self.record("good")
        self.lore("rebuild")
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("database retries", "index pool exhaustion"),
                        encoding="utf-8")
        os.utime(path, (1000000, 1000000))
        result = self.lore("search", "exhaustion")
        self.assertIn("id: good", result.stdout)
        renamed = path.with_name("renamed.md")
        renamed.write_text(text.replace("id: good", "id: renamed"), encoding="utf-8")
        os.utime(renamed, (1000000, 1000000))
        path.unlink()
        result = self.lore("search", "认证")
        self.assertIn("id: renamed", result.stdout)

    def test_wiped_index_metadata_self_repairs(self):
        self.record("good")
        self.lore("rebuild")
        db = self.archive / ".lore" / "lore.db"
        with contextlib.closing(sqlite3.connect(db)) as con:
            con.execute("DROP TABLE index_meta")
            con.commit()
        result = self.lore("search", "认证")
        self.assertEqual(result.returncode, 0)
        self.assertIn("id: good", result.stdout)

    def test_no_staging_file_left_after_rebuild(self):
        self.record("good")
        self.lore("rebuild")
        self.assertTrue((self.archive / ".lore" / "lore.db").exists())
        self.assertEqual(list((self.archive / ".lore").glob("*.building*")), [])

    def test_metrics_full_survives_without_current_records(self):
        self.record("gone", status="superseded")
        result = self.lore("metrics", "--full")
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("N/A", result.stdout)

    def test_new_record_topics_round_trip(self):
        result = self.lore("new", "--title", "Hostile topics", "--type", "lesson",
                           "--importance", "normal",
                           "--topics", "on, null, api: gateway, *backend")
        self.assertEqual(result.returncode, 0, result.stderr)
        created = self.archive / "memory" / "lessons" / "hostile-topics.md"
        text = created.read_text(encoding="utf-8")
        self.assertEqual(text.count("topics:"), 1)
        meta = yaml.safe_load(text.split("---\n")[1])
        self.assertEqual(meta["topics"],
                         ["on", "null", "api: gateway", "*backend"])

    def test_init_command_creates_archive(self):
        target = self.root / "new-archive"
        result = subprocess.run(
            [sys.executable, "-B", str(LORE_PY), "init", str(target), "--json"],
            capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["created"])
        self.assertTrue((target / "memory" / "README.md").exists())

    def test_new_json_output(self):
        result = self.lore("new", "--title", "JSON record", "--type", "lesson",
                           "--importance", "normal", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["created"])
        self.assertEqual(payload["id"], "lore_json_record")

    def test_new_explicit_id(self):
        result = self.lore("new", "--id", "stable.record-id", "--title", "Stable id",
                           "--type", "lesson", "--importance", "normal", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["id"], "stable.record-id")

    def test_new_dry_run_json_writes_nothing(self):
        result = self.lore("new", "--title", "Preview record", "--type", "lesson",
                           "--importance", "normal", "--dry-run", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["created"])
        self.assertTrue(payload["dry_run"])
        self.assertIn("# Preview record", payload["content"])
        self.assertFalse((self.archive / "memory" / "lessons" / "preview-record.md").exists())

    def test_relate_command_updates_canonical_record(self):
        source = self.record("source")
        self.record("target")
        result = self.lore("relate", "source", "depends_on", "target")
        self.assertEqual(result.returncode, 0, result.stderr)
        meta = yaml.safe_load(source.read_text(encoding="utf-8").split("---\n")[1])
        self.assertEqual(meta["relations"], {"depends_on": ["target"]})

    def test_supersede_command_updates_old_and_new_records(self):
        old = self.record("old")
        new = self.record("new")
        result = self.lore("supersede", "old", "--by", "new")
        self.assertEqual(result.returncode, 0, result.stderr)
        old_meta = yaml.safe_load(old.read_text(encoding="utf-8").split("---\n")[1])
        new_meta = yaml.safe_load(new.read_text(encoding="utf-8").split("---\n")[1])
        self.assertEqual(old_meta["status"], "superseded")
        self.assertEqual(new_meta["relations"]["supersedes"], ["old"])

    def test_status_command_updates_record(self):
        path = self.record("record")
        result = self.lore("status", "record", "resolved")
        self.assertEqual(result.returncode, 0, result.stderr)
        meta = yaml.safe_load(path.read_text(encoding="utf-8").split("---\n")[1])
        self.assertEqual(meta["status"], "resolved")

        result = self.lore("status", "record", "superseded")
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)

    def test_search_json_output(self):
        self.record("good")
        result = self.lore("search", "database", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["id"], "good")

    def test_show_json_output(self):
        self.record("good")
        result = self.lore("show", "good", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["id"], "good")
        self.assertEqual(payload["topics"], ["testing"])
        self.assertIn("gateway retries", payload["body"])

    def test_list_json_and_positive_limit(self):
        self.record("good")
        result = self.lore("list", "--json", "--type", "lesson", "--topic", "testing")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["records"][0]["id"], "good")

        result = self.lore("list", "--limit", "0")
        self.assertEqual(result.returncode, 2)
        self.assertIn("positive integer", result.stderr)

    def test_list_selects_retired_status(self):
        self.record("old", status="deprecated")
        result = self.lore("list", "--status", "deprecated", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual([record["id"] for record in payload["records"]], ["old"])

    def test_list_selects_importance(self):
        self.record("normal", importance="normal")
        self.record("critical", importance="critical")
        result = self.lore("list", "--importance", "critical", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual([item["id"] for item in payload["records"]], ["critical"])

    def test_backlinks_json(self):
        self.record("source", relations={"depends_on": ["target"]})
        self.record("target")
        result = self.lore("backlinks", "target", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["incoming"][0]["id"], "source")

    def test_rename_command_updates_backlinks(self):
        self.record("source", relations={"related_to": ["old"]})
        self.record("old")
        result = self.lore("rename", "old", "renamed")
        self.assertEqual(result.returncode, 0, result.stderr)
        graph = self.lore("backlinks", "renamed", "--json")
        self.assertEqual(json.loads(graph.stdout)["incoming"][0]["id"], "source")


@unittest.skipUnless(os.name == "posix", "POSIX launcher integration")
class InstallerTests(E2ETestCase):
    def setUp(self):
        super().setUp()
        self.home = Path(self.env["HOME"])
        self.bin_dir = self.home / ".local" / "bin"
        self.rc = self.home / ".zshrc"

    def install(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(INSTALL_PY), *args],
            capture_output=True, text=True, env=self.env)

    def test_install_launcher_and_profile_then_clean_uninstall(self):
        result = self.install(str(self.archive), "--shell-rc")
        self.assertEqual(result.returncode, 0, result.stderr)
        launcher = self.bin_dir / "lore"
        self.assertTrue(launcher.exists())
        text = launcher.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("#!/bin/sh"))
        self.assertIn("exec ", text)
        self.assertIn("'" + str(LORE_PY) + "'", text)
        profile = self.rc.read_text(encoding="utf-8")
        self.assertIn("export LORE_ROOT=", profile)
        self.assertIn("# added by lore tools/install.py", profile)
        self.assertIn("'" + str(self.archive) + "'", profile)
        result = subprocess.run(
            ["/bin/sh", "-c", '. "$1"; exec "$2" stats', "sh",
             str(self.rc), str(launcher)],
            capture_output=True, text=True, env=self.env, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"root: {self.archive}", result.stdout)
        result = self.install(str(self.archive), "--shell-rc", "--uninstall")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(launcher.exists())
        self.assertNotIn("LORE_ROOT", self.rc.read_text(encoding="utf-8"))

    def test_unrelated_launcher_and_profile_lines_are_preserved(self):
        self.bin_dir.mkdir(parents=True)
        unrelated = self.bin_dir / "lore"
        unrelated.write_text("#!/bin/sh\necho other\n", encoding="utf-8")
        result = self.install(str(self.archive))
        self.assertEqual(result.returncode, 1)
        self.assertIn("Refusing", result.stderr)
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "#!/bin/sh\necho other\n")
        unrelated.unlink()
        launcher = self.bin_dir / "lore"
        self.assertEqual(self.install(str(self.archive), "--shell-rc").returncode, 0)
        self.rc.write_text(
            self.rc.read_text(encoding="utf-8") + "# my stuff\nalias ll='ls -la'\n",
            encoding="utf-8")
        result = self.install(str(self.archive), "--shell-rc", "--uninstall")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(launcher.exists())
        profile = self.rc.read_text(encoding="utf-8")
        self.assertNotIn("LORE_ROOT", profile)
        self.assertIn("# my stuff", profile)
        self.assertIn("alias ll", profile)


if __name__ == "__main__":
    unittest.main()
