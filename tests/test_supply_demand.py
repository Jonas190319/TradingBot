import importlib.util
import pathlib
import sys
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

path = pathlib.Path(__file__).resolve().parents[1] / "services" / "mt5-engine" / "supply_demand.py"
spec = importlib.util.spec_from_file_location("supply_demand_test_module", path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


@dataclass
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float


def make_bars(prices):
    start = datetime(2026, 10, 9, tzinfo=timezone.utc)
    return [Bar(start + timedelta(minutes=5 * i), op, hi, lo, cl)
            for i, (op, hi, lo, cl) in enumerate(prices)]


class SupplyDemandTests(unittest.TestCase):
    def test_demand_zone_after_confirmed_departure(self):
        bars = make_bars([(100, 101, 99, 100), (100, 100.5, 99.5, 100),
                          (100, 103, 100, 102.5), (102.5, 104, 102, 103)])
        zones = module.detect_zones(bars, atr=1)
        self.assertTrue(any(z.side == "demand" and z.lower == 99.5 for z in zones))

    def test_zone_not_confirmed_before_departure(self):
        bars = make_bars([(100, 101, 99, 100), (100, 100.5, 99.5, 100)])
        self.assertEqual(module.detect_zones(bars, atr=1), [])

    def test_invalidation(self):
        bars = make_bars([(100, 101, 99, 100), (100, 100.5, 99.5, 100),
                          (100, 103, 100, 102.5), (102.5, 103, 98, 98.5)])
        self.assertFalse(any(z.side == "demand" and z.lower == 99.5
                             for z in module.detect_zones(bars, atr=1)))


if __name__ == "__main__":
    unittest.main()
