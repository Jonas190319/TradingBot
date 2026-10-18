"""Offline research outcome tests. No MT5 dependency."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "mt5-engine"))
from research_outcomes import evaluate_outcome, summarize_outcomes


class ResearchOutcomesTests(unittest.TestCase):
    def test_long_target(self):
        r = evaluate_outcome("long", 100, 99, 102, [{"high": 102, "low": 100}])
        self.assertEqual((r["outcome"], r["r"]), ("target", 2.0))

    def test_short_stop(self):
        r = evaluate_outcome("short", 100, 101, 98, [{"high": 101, "low": 99}])
        self.assertEqual((r["outcome"], r["r"]), ("stop", -1.0))

    def test_both_touched_ambiguous(self):
        r = evaluate_outcome("long", 100, 99, 102, [{"high": 103, "low": 98}])
        self.assertEqual((r["outcome"], r["r"]), ("ambiguous", None))

    def test_unresolved(self):
        r = evaluate_outcome("long", 100, 99, 102, [{"high": 101, "low": 99.5}])
        self.assertEqual(r["outcome"], "unresolved")

    def test_summary_excludes_unknown(self):
        rows = [evaluate_outcome("long", 100, 99, 102, [{"high": 102, "low": 100}]),
                evaluate_outcome("long", 100, 99, 102, [{"high": 100, "low": 99}]),
                evaluate_outcome("long", 100, 99, 102, [{"high": 103, "low": 98}])]
        summary = summarize_outcomes(rows)
        self.assertEqual(summary["resolved"], 2)
        self.assertEqual(summary["ambiguous"], 1)
        self.assertEqual(summary["win_rate"], 0.5)
        self.assertEqual(summary["mean_r"], 0.5)


if __name__ == "__main__":
    unittest.main()
