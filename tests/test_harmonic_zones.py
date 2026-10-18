"""Tests for bounded harmonic completion zones, independent of MT5."""
import unittest
from services.decision_engine.harmonic_patterns import classify_completion_zone


class HarmonicZonesTests(unittest.TestCase):
    def test_bullish_inside_zone(self):
        self.assertEqual(classify_completion_zone("long", 100, 99.4, 1)["status"], "entry_zone")

    def test_bullish_developing_above_zone(self):
        self.assertEqual(classify_completion_zone("long", 100, 101, 1)["status"], "developing")

    def test_bullish_invalid_below_threshold(self):
        self.assertEqual(classify_completion_zone("long", 100, 98.4, 1)["status"], "invalidated")

    def test_bearish_invalid_above_threshold(self):
        self.assertEqual(classify_completion_zone("short", 100, 101.6, 1)["status"], "invalidated")

    def test_bearish_below_zone_not_invalid(self):
        self.assertEqual(classify_completion_zone("short", 100, 99, 1)["status"], "developing")

    def test_invalid_settings(self):
        with self.assertRaises(ValueError):
            classify_completion_zone("long", 100, 100, 1, 1.5, 0.75)


if __name__ == "__main__":
    unittest.main()
