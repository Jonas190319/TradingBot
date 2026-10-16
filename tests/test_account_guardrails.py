import importlib.util
import pathlib
import sys
import unittest
from types import SimpleNamespace

path = pathlib.Path(__file__).resolve().parents[1] / "services" / "mt5-engine" / "account_guardrails.py"
spec = importlib.util.spec_from_file_location("account_guardrails_test", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def account(**overrides):
    values = dict(balance=10000, equity=10000, margin_free=9000, margin=1000, margin_level=1000)
    values.update(overrides)
    return SimpleNamespace(**values)


class DemoGuardrailsTests(unittest.TestCase):
    def test_healthy(self):
        self.assertTrue(mod.evaluate_account_health(account()).demo_orders_allowed)

    def test_empty_balance_shadow_continues(self):
        result = mod.evaluate_account_health(account(balance=0, equity=0, margin_free=0))
        self.assertFalse(result.demo_orders_allowed)
        self.assertTrue(result.shadow_allowed)
        self.assertIn("demo_balance_empty", result.reasons)

    def test_low_margin(self):
        result = mod.evaluate_account_health(account(margin_level=120))
        self.assertFalse(result.demo_orders_allowed)
        self.assertIn("margin_level_below_minimum", result.reasons)

    def test_zero_used_margin_does_not_false_alarm(self):
        self.assertTrue(mod.evaluate_account_health(account(margin=0, margin_level=0)).demo_orders_allowed)

    def test_invalid_metric_fails_closed(self):
        self.assertFalse(mod.evaluate_account_health(account(equity=float("nan"))).demo_orders_allowed)


if __name__ == "__main__":
    unittest.main()
