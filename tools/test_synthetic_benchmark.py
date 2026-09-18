import importlib.util
from pathlib import Path
import unittest


SOURCE = Path(__file__).with_name("run_synthetic_benchmark.py")
spec = importlib.util.spec_from_file_location("synthetic_benchmark", SOURCE)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class SyntheticBenchmarkTests(unittest.TestCase):
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
