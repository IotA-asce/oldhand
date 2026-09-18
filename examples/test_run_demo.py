"""Regression tests for the self-contained synthetic Lore demonstration."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest


EXAMPLES = Path(__file__).resolve().parent
DEMO = EXAMPLES / "run_demo.py"
SAMPLE = EXAMPLES / "sample-project"


class SyntheticDemoTests(unittest.TestCase):
    def test_demo_is_offline_and_explains_the_retrieved_constraint(self):
        before = sorted(path.relative_to(SAMPLE) for path in SAMPLE.rglob("*"))
        completed = subprocess.run(
            [sys.executable, str(DEMO)],
            check=True,
            capture_output=True,
            text=True,
            cwd=EXAMPLES.parent,
        )
        after = sorted(path.relative_to(SAMPLE) for path in SAMPLE.rglob("*"))

        self.assertEqual(before, after, "the source sample must never be modified")
        self.assertIn("no network, account, model, or real project data", completed.stdout)
        self.assertIn("Before: no environment file selected", completed.stdout)
        self.assertIn("postgresql://demo-user@database.invalid/synthetic_app", completed.stdout)
        self.assertIn("<missing: staging must declare it explicitly>", completed.stdout)
        self.assertIn("Retrieved: synthetic_environment_config_replaces_defaults", completed.stdout)
        self.assertIn("Evidence: verified", completed.stdout)
        self.assertFalse((SAMPLE / ".lore").exists())

    def test_sample_is_explicitly_synthetic(self):
        notice = (SAMPLE / "SYNTHETIC_EXAMPLE.md").read_text(encoding="utf-8")
        record = next((SAMPLE / "memory").rglob("*.md")).read_text(encoding="utf-8")
        self.assertIn("fictional", notice.lower())
        self.assertIn(".invalid", notice)
        self.assertIn("Synthetic example", record)


if __name__ == "__main__":
    unittest.main()
