import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from oldhand.constants import SETUP_END, SETUP_GUIDANCE, SETUP_START
from oldhand.harness import setup_harness


class CompactSetupTests(unittest.TestCase):
    def test_compact_guidance_covers_selective_memory_use(self):
        self.assertLess(len(SETUP_GUIDANCE.splitlines()) + 2, 25)
        for phrase in ('task-specific', 'summaries', 'oldhand show', 'record nothing',
                       'critical', 'evidence', 'oldhand guide writing'):
            self.assertIn(phrase, SETUP_GUIDANCE)

    def test_existing_blocks_upgrade_and_undo_without_changing_user_instructions(self):
        targets = {
            'claude': '.claude/rules/oldhand.md',
            'cursor': '.cursor/rules/oldhand.mdc',
            'codex': 'AGENTS.md',
            'opencode': 'AGENTS.md',
        }
        prefix, suffix = 'Keep these instructions.\n', 'Keep these trailing notes.\n'
        old_block = SETUP_START + '\n## Oldhand memory\n\nPrior guidance.\n' + SETUP_END + '\n'
        for harness, relative in targets.items():
            with self.subTest(harness=harness), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                before = prefix + old_block + suffix
                target.write_text(before, encoding='utf-8')
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(setup_harness(root, harness), 0)
                    self.assertEqual(target.read_text(), before)
                    self.assertEqual(setup_harness(root, harness, apply=True), 0)
                    applied = target.read_bytes()
                    self.assertTrue(applied.startswith(prefix.encode()))
                    self.assertTrue(applied.endswith(suffix.encode()))
                    self.assertIn(SETUP_GUIDANCE.encode(), applied)
                    self.assertNotIn(b'Prior guidance.', applied)
                    self.assertEqual(setup_harness(root, harness, apply=True), 0)
                    self.assertEqual(target.read_bytes(), applied)
                    self.assertEqual(setup_harness(root, harness, undo=True), 0)
                    self.assertEqual(target.read_bytes(), applied)
                    self.assertEqual(setup_harness(root, harness, apply=True, undo=True), 0)
                    self.assertEqual(target.read_text(), prefix + suffix)
                    self.assertEqual(setup_harness(root, harness, apply=True, undo=True), 0)
                    self.assertEqual(target.read_text(), prefix + suffix)
