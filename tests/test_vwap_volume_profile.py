"""Pure offline tests; never connect to MT5 or place orders."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "services" / "mt5-engine" / "vwap_volume_profile.py"
spec = importlib.util.spec_from_file_location("vwap_volume_profile", path)
import sys
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
Bar, Profile = module.Bar, module.Profile


class StrategyTests(unittest.TestCase):
    def test_vwap_volume_weighted(self):
        bars = [Bar(11, 9, 10, 1), Bar(21, 19, 20, 3)]
        self.assertAlmostEqual(module.vwap(bars), 17.5)

    def test_prior_day_profile(self):
        p = module.volume_profile([Bar(100, 100, 100, 70), Bar(101, 101, 101, 20), Bar(102, 102, 102, 10)], 1)
        self.assertEqual((p.val, p.poc, p.vah), (100, 100, 100))
        self.assertAlmostEqual(p.total_volume, 100)

    def test_reversal(self):
        p = Profile(110, 105, 100, 100)
        bars = [Bar(106, 102, 104, 10), Bar(105, 99, 102, 10)]
        signals = module.detect_signals(bars, p, 0.1)
        self.assertTrue(any(s.strategy == "VALUE_AREA_REVERSAL" and s.side == "long" for s in signals))

    def test_breakout(self):
        p = Profile(110, 105, 100, 100)
        bars = [Bar(109, 106, 108, 10), Bar(113, 109, 112, 10)]
        signals = module.detect_signals(bars, p, 0.1)
        self.assertTrue(any(s.strategy == "VALUE_AREA_BREAKOUT" and s.side == "long" for s in signals))

    def test_no_volume(self):
        with self.assertRaises(ValueError):
            module.vwap([Bar(1, 1, 1, 0)])

    def test_bad_bar(self):
        with self.assertRaises(ValueError):
            module.volume_profile([Bar(1, 2, 1, 10)], 0.1)


if __name__ == "__main__":
    unittest.main()
