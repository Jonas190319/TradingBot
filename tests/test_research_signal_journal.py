"""Offline tests: research signal IDs and fail-closed validation."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "mt5-engine"))
from research_signal_journal import journal_record, records_from_scan


class ResearchJournalTests(unittest.TestCase):
    def base(self):
        return dict(account_server="Demo-Server", account_login=1234,
                    market="EURUSD", broker_symbol="EURUSD",
                    strategy="opening_range", side="long",
                    bar_time_utc=datetime(2026, 10, 19, 17, 0, tzinfo=timezone.utc),
                    entry=1.10, stop_loss=1.09, take_profit=1.12,
                    source="shadow_strategist")

    def test_stable_id_across_volatile_values(self):
        a = self.base()
        b = dict(a, entry=1.101, setup_score=None) if False else dict(a, entry=1.101)
        self.assertEqual(journal_record(**a)["signal_id"], journal_record(**b)["signal_id"])

    def test_other_bar_has_different_id(self):
        a = self.base()
        b = dict(a, bar_time_utc=datetime(2026, 10, 19, 17, 5, tzinfo=timezone.utc))
        self.assertNotEqual(journal_record(**a)["signal_id"], journal_record(**b)["signal_id"])

    def test_invalid_risk_rejected(self):
        with self.assertRaises(ValueError):
            journal_record(**dict(self.base(), stop_loss=1.11))

    def test_unregistered_strategy_rejected(self):
        with self.assertRaises(ValueError):
            journal_record(**dict(self.base(), strategy="not_a_strategy"))

    def test_both_engines(self):
        t = self.base()["bar_time_utc"]
        rows = records_from_scan("Demo-Server", 1234, "EURUSD", "EURUSD", t,
            {"opening_range": dict(side="long", entry=1.1, stop=1.09, target=1.12, score=70)},
            [dict(strategy="VWAP_RETEST", side="short", entry=1.1, stop=1.11, target=1.08)])
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["source"] for r in rows}, {"shadow_strategist", "profile_scanner"})


if __name__ == "__main__":
    unittest.main()
