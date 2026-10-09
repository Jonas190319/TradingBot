import unittest
import importlib.util
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "services" / "decision-engine" / "shadow_quality_audit.py"
spec = importlib.util.spec_from_file_location("shadow_quality_audit", MODULE)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def row(candidate, r, **extra):
    return {
        "candidate_id": candidate, "strategy": "trend_pullback", "symbol": "EURUSD",
        "was_executed": False, "completed_at": "2026-10-09T17:20:00+00:00",
        "realized_r": r, "metadata": {"sampled": True}, **extra,
    }


class ShadowAuditTests(unittest.TestCase):
    def test_deduplicates_and_excludes_nonfinite(self):
        result = audit.audit_shadow_outcomes([
            row("a", 1.5), row("a", 1.5), row("b", -1.0),
            row("c", float("nan")), row("d", 2, was_executed=True),
        ])
        self.assertEqual(result["groups"][0]["n"], 2)
        self.assertAlmostEqual(result["groups"][0]["total_r"], 0.5)
        self.assertFalse(result["groups"][0]["eligible_for_execution"])
        self.assertEqual(result["excluded"]["missing_or_duplicate_candidate_id"], 1)
        self.assertEqual(result["excluded"]["nonfinite_r"], 1)

    def test_small_sample_is_not_approved(self):
        result = audit.audit_shadow_outcomes([row("a", 2)])
        self.assertIn("insufficient_sample", result["groups"][0]["warnings"])
        self.assertFalse(result["groups"][0]["eligible_for_auto_tuning"])

    def test_zero_losses_has_no_infinite_json_value(self):
        result = audit.audit_shadow_outcomes([row("a", 2)])
        self.assertIsNone(result["groups"][0]["profit_factor"])
        self.assertTrue(result["groups"][0]["profit_factor_unbounded"])


if __name__ == "__main__":
    unittest.main()
