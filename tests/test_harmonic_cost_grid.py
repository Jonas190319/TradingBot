"""Offline fixed-target cost sensitivity tests; no MT5 or orders."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "mt5-engine"))
from sequential_research_execution import simulate_signals


class CostGridTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"time": 300 * i, "open": 100.0, "high": 101.0, "low": 99.8, "close": 100.0}
            for i in range(5)
        ]
        self.rows[2].update(open=100.0, high=103.0, low=99.9, close=102.0)
        self.signals = [{"bar_index": 1, "side": "long", "stop": 99.0,
                         "target_rr": 2.0, "signal_id": "same"}]

    def test_cost_reduces_fixed_target_r(self):
        outcomes = [
            simulate_signals(self.rows, self.signals, cost_ticks=c,
                             tick_size=0.01, cost_model="fixed_rr")
            for c in (0, 2, 8)
        ]
        self.assertEqual([x[0]["outcome"] for x in outcomes], ["target"] * 3)
        values = [x[0]["r"] for x in outcomes]
        self.assertAlmostEqual(values[0], 2.0)
        self.assertAlmostEqual(values[1], 1.98)
        self.assertAlmostEqual(values[2], 1.92)
        self.assertEqual([x[0]["signal_id"] for x in outcomes], ["same"] * 3)

    def test_legacy_behavior_unchanged(self):
        a = simulate_signals(self.rows, self.signals, cost_ticks=2, tick_size=0.01)
        b = simulate_signals(self.rows, self.signals, cost_ticks=2,
                             tick_size=0.01, cost_model="legacy")
        self.assertEqual(a, b)

    def test_invalid_cost_model_rejected(self):
        with self.assertRaises(ValueError):
            simulate_signals(self.rows, self.signals, cost_model="unknown")


if __name__ == "__main__":
    unittest.main()
