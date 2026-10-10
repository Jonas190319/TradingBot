"""Regression tests for research strategy integration. Run: python -m unittest discover -s tests"""
import importlib
import unittest
from datetime import datetime, timezone

from services.decision_engine.models import MarketSnapshot, Regime
from services.decision_engine.strategists import (
    CORE_STRATEGISTS, SupplyDemandStrategist, RangeTradingStrategist,
    VWAPReclaimStrategist, MeanReversionStrategist,
)


def snapshot(**features):
    base = {"atr": 1.0}
    base.update(features)
    return MarketSnapshot(datetime(2026, 10, 9, tzinfo=timezone.utc), "TEST",
                          102.0, 102.02, 0.02, base)


class NewStrategiesTests(unittest.TestCase):
    def test_registered(self):
        names = {s.name for s in CORE_STRATEGISTS}
        self.assertTrue({"supply_demand", "range_trading", "vwap_reclaim",
                         "mean_reversion"}.issubset(names))

    def test_supply_demand_requires_reaction(self):
        s = snapshot(sd_zone_present=True, sd_zone_side="demand",
                     sd_zone_lower=100, sd_zone_upper=101, sd_zone_reaction=False)
        self.assertIsNone(SupplyDemandStrategist().evaluate(s, Regime.TREND))

    def test_supply_demand_candidate(self):
        s = snapshot(sd_zone_present=True, sd_zone_side="demand",
                     sd_zone_lower=100, sd_zone_upper=101, sd_zone_reaction=True,
                     sd_zone_departure_atr=2, sd_zone_touches=1)
        c = SupplyDemandStrategist().evaluate(s, Regime.TREND)
        self.assertIsNotNone(c)
        self.assertLess(c.stop_loss, c.entry)
        self.assertGreater(c.take_profit_1, c.entry)

    def test_vwap_fails_closed_without_volume(self):
        self.assertIsNone(VWAPReclaimStrategist().evaluate(snapshot(), Regime.TREND))

    def test_mean_reversion_only_range(self):
        s = snapshot(mean_deviation_atr=-2.5, reversal_direction=1)
        self.assertIsNone(MeanReversionStrategist().evaluate(s, Regime.TREND))
        self.assertIsNotNone(MeanReversionStrategist().evaluate(s, Regime.RANGE))

    def test_range_requires_boundary_rejection(self):
        s = snapshot(range_low=100, range_high=106, last_close=102, last_open=101)
        self.assertIsNone(RangeTradingStrategist().evaluate(s, Regime.RANGE))


if __name__ == "__main__":
    unittest.main()
