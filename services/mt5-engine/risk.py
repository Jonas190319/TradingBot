from dataclasses import dataclass

@dataclass(frozen=True)
class RiskPolicy:
    max_risk_per_trade_pct: float = 0.5
    max_daily_loss_pct: float = 1.5
    max_weekly_loss_pct: float = 3.0
    quality_threshold: float = 80.0


def can_trade(*, quality_score: float, daily_loss_pct: float, weekly_loss_pct: float, live_enabled: bool, mode: str, policy: RiskPolicy = RiskPolicy()):
    if mode not in {"DEMO", "LIVE"}:
        return False, "Trading mode does not permit execution"
    if mode == "LIVE" and not live_enabled:
        return False, "Live execution hard gate is disabled"
    if quality_score < policy.quality_threshold:
        return False, "Quality score below threshold"
    if daily_loss_pct >= policy.max_daily_loss_pct:
        return False, "Daily loss limit reached"
    if weekly_loss_pct >= policy.max_weekly_loss_pct:
        return False, "Weekly loss limit reached"
    return True, "Approved by base risk policy"
