import importlib.util
from pathlib import Path
import unittest
from unittest import mock


SOURCE = Path(__file__).resolve().parents[1] / "tools" / "run_synthetic_benchmark.py"
spec = importlib.util.spec_from_file_location("synthetic_benchmark", SOURCE)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class SyntheticBenchmarkTests(unittest.TestCase):
    def test_fixture_digest_is_independent_of_checkout_line_endings(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = root / "fixture"
            fixture.mkdir()
            note = fixture / "note.md"
            queries = root / "queries.json"
            with mock.patch.object(benchmark, "FIXTURE", fixture), \
                    mock.patch.object(benchmark, "QUERIES", queries):
                note.write_bytes(b"# Synthetic\n\nA finding.\n")
                queries.write_bytes(b"{}\n")
                before = benchmark.fixture_digest()
                note.write_bytes(note.read_bytes().replace(b"\n", b"\r\n"))
                queries.write_bytes(b"{}\r\n")
                self.assertEqual(benchmark.fixture_digest(), before)

    def test_checked_in_baseline_matches_deterministic_fixture(self):
        result = benchmark.run_benchmark()
        self.assertEqual(
            benchmark.RESULTS.read_text(encoding="utf-8"),
            benchmark.canonical_json(result),
        )
        self.assertEqual(result["query_count"], 6)
        self.assertEqual(result["metrics"]["recall_at_5"], 1.0)


if __name__ == "__main__":
    unittest.main()
