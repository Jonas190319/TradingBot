import importlib.util
import pathlib
import unittest

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "services" / "decision-engine" / "harmonic_patterns.py"
spec = importlib.util.spec_from_file_location("harmonic_patterns", MODULE_PATH)
import sys
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
Pivot, detect = module.Pivot, module.detect_xabcd


def pivots(values):
    return [Pivot(f"2026-10-09T00:{i:02d}:00+00:00", value, "low" if i % 2 == 0 else "high")
            for i, value in enumerate(values)]


class HarmonicDetectorTests(unittest.TestCase):
    def test_gartley_bullish(self):
        found = detect(pivots([100, 110, 103.82, 107, 102.14]))
        self.assertIn("gartley", [match.pattern for match in found])
        self.assertTrue(all(match.direction == "long" for match in found))

    def test_bat_bullish(self):
        found = detect(pivots([100, 110, 105, 108, 101.14]))
        self.assertIn("bat", [match.pattern for match in found])

    def test_reject_noncausal_order(self):
        rows = pivots([100, 110, 103.82, 107, 102.14])
        rows[2] = Pivot(rows[0].timestamp, rows[2].price, rows[2].kind)
        self.assertEqual(detect(rows), [])

    def test_reject_unconfirmed_structure(self):
        rows = pivots([100, 110, 103.82, 107, 102.14])
        rows[2] = Pivot(rows[2].timestamp, rows[2].price, "high")
        self.assertEqual(detect(rows), [])

    def test_no_trade_api(self):
        self.assertFalse(hasattr(module, "place_order"))


if __name__ == "__main__":
    unittest.main()
