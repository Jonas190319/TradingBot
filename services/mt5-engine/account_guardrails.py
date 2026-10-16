"""Read-only demo account health checks. No broker order capability."""
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class AccountHealth:
    shadow_allowed: bool
    demo_orders_allowed: bool
    reasons: tuple[str, ...]
    balance: float
    equity: float
    margin_free: float
    margin_level: float | None


def evaluate_account_health(account, *, min_equity: float = 100.0,
                            min_free_margin: float = 100.0,
                            min_margin_level: float = 200.0) -> AccountHealth:
    """Fail closed for order eligibility; keep read-only shadow collection available."""
    fields = {}
    for name in ("balance", "equity", "margin_free"):
        try:
            fields[name] = float(getattr(account, name))
        except (ValueError, TypeError, AttributeError):
            fields[name] = float("nan")
    try:
        margin_level = float(getattr(account, "margin_level", None))
    except (ValueError, TypeError):
        margin_level = None
    reasons = []
    if any(not isfinite(v) for v in fields.values()):
        reasons.append("invalid_account_metrics")
    else:
        if fields["balance"] <= 0:
            reasons.append("demo_balance_empty")
        if fields["equity"] < min_equity:
            reasons.append("equity_below_minimum")
        if fields["margin_free"] < min_free_margin:
            reasons.append("free_margin_below_minimum")
    # MT5 may report zero margin level when no positions/margin are used.
    try:
        used_margin = float(getattr(account, "margin", 0))
    except (TypeError, ValueError):
        used_margin = float("nan")
    if not isfinite(used_margin) or used_margin < 0:
        reasons.append("invalid_used_margin")
    elif used_margin > 0 and (margin_level is None or not isfinite(margin_level)
                              or margin_level < min_margin_level):
        reasons.append("margin_level_below_minimum")
    return AccountHealth(True, not reasons, tuple(reasons),
                         fields["balance"], fields["equity"], fields["margin_free"],
                         margin_level)
