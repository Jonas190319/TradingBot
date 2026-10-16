import importlib.util
import pathlib
import sys
import unittest

path = pathlib.Path(__file__).resolve().parents[1] / "services" / "mt5-engine" / "risk_sizing.py"
spec = importlib.util.spec_from_file_location("risk_sizing_test_module", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

BASE = dict(equity=10000, entry=100, stop_loss=99, tick_size=0.01,
            tick_value_per_lot=0.1, min_lot=0.01, max_lot=10, lot_step=0.01,
            free_margin=10000, margin_per_lot=1000, open_positions=0,
            existing_open_risk=0)

class RiskSizingTests(unittest.TestCase):
    def decide(self, **changes):
        return mod.size_candidate(**(BASE | changes))

    def test_risk_cap_and_step(self):
        d = self.decide()
        self.assertTrue(d.approved)
        self.assertLessEqual(d.risk_amount, 50)
        self.assertEqual(d.lots, 5.0)

    def test_aggregate_limit(self):
        d = self.decide(existing_open_risk=145)
        self.assertTrue(d.approved)
        self.assertLessEqual(d.risk_amount, 5)

    def test_positions_cap(self):
        self.assertEqual(self.decide(open_positions=5).reason, "max_positions_reached")

    def test_below_minimum_lot(self):
        self.assertFalse(self.decide(equity=100, min_lot=0.1).approved)

    def test_margin_cap(self):
        d = self.decide(free_margin=100)
        self.assertTrue(d.approved)
        self.assertEqual(d.lots, 0.1)

    def test_invalid_data_fails_closed(self):
        self.assertFalse(self.decide(tick_value_per_lot=float("nan")).approved)
        self.assertFalse(self.decide(entry=99, stop_loss=99).approved)
        self.assertFalse(self.decide(risk_pct=1.0).approved)

if __name__ == "__main__":
    unittest.main()
