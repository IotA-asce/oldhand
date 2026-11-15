import contextlib
import io
import unittest
from unittest import mock

from oldhand import cli


class GuideTests(unittest.TestCase):
    def run_guide(self, *arguments):
        output = io.StringIO()
        with mock.patch('sys.argv', ['oldhand', 'guide', *arguments]), \
                mock.patch.object(cli, 'workspace_root', side_effect=AssertionError('archive accessed')), \
                mock.patch.object(cli, 'record_daily_metrics', side_effect=AssertionError('metrics written')), \
                contextlib.redirect_stdout(output):
            self.assertEqual(cli.main(), 0)
        return output.getvalue()

    def test_topic_index_needs_no_archive(self):
        output = self.run_guide()
        for topic in ('writing', 'vocabulary', 'importance', 'lifecycle', 'exclusions'):
            self.assertIn('oldhand guide ' + topic, output)

    def test_each_topic_renders_offline(self):
        for topic in ('writing', 'vocabulary', 'importance', 'lifecycle', 'exclusions'):
            with self.subTest(topic=topic):
                self.assertGreater(len(self.run_guide(topic)), 200)

    def test_lifecycle_has_executable_walkthrough(self):
        output = self.run_guide('lifecycle')
        for command in ('oldhand init', 'new --id guide-example', 'search', 'status guide-example historical'):
            self.assertIn(command, output)

    def test_unknown_topic_reports_valid_choices(self):
        errors = io.StringIO()
        with mock.patch('sys.argv', ['oldhand', 'guide', 'missing']), \
                contextlib.redirect_stderr(errors), self.assertRaises(SystemExit) as raised:
            cli.main()
        self.assertEqual(raised.exception.code, 2)
        self.assertIn('lifecycle', errors.getvalue())
