import unittest
from services.decision_engine.strategists import CORE_STRATEGISTS

class RegistryTest(unittest.TestCase):
    def test_strategy_names(self):
        expected = {'opening_range', 'trend_pullback', 'compression_breakout', 'liquidity_sweep', 'supply_demand', 'range_trading', 'vwap_reclaim', 'mean_reversion', 'harmonic_gartley', 'harmonic_bat', 'harmonic_butterfly', 'harmonic_crab', 'harmonic_shark'}
        self.assertEqual({s.name for s in CORE_STRATEGISTS}, expected)

if __name__ == '__main__':
    unittest.main()
