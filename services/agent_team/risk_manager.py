from __future__ import annotations

from dataclasses import dataclass

from .models import Decision, PortfolioState, RiskVerdict, TradeProposal


@dataclass(frozen=True)
class RiskPolicy:
    max_risk_per_trade_pct: float = 0.50
    max_daily_loss_pct: float = 1.50
    max_weekly_loss_pct: float = 3.00
    max_drawdown_pct: float = 8.00
    max_open_risk_pct: float = 2.00
    max_open_positions: int = 4
    max_symbol_exposure_pct: float = 1.00
    max_currency_exposure_pct: float = 2.00
    min_quality_score: float = 80.0
    max_spread_points: float = 50.0


class RiskManager:
    name = "risk"

    def __init__(self, policy: RiskPolicy | None = None) -> None:
        self.policy = policy or RiskPolicy()

    def evaluate(self, proposal: TradeProposal | None, portfolio: PortfolioState,
                 spread_points: float | None = None) -> RiskVerdict:
        if proposal is None:
            return RiskVerdict(Decision.NO_TRADE, 0.0, ("Portfolio manager produced no qualifying trade.",), False)

        reasons: list[str] = []
        veto = False
        p = self.policy

        if proposal.quality_score < p.min_quality_score:
            reasons.append(f"Quality {proposal.quality_score:.1f} below {p.min_quality_score:.1f}.")
            veto = True
        if portfolio.daily_pnl_pct <= -p.max_daily_loss_pct:
            reasons.append("Daily loss limit reached.")
            veto = True
        if portfolio.weekly_pnl_pct <= -p.max_weekly_loss_pct:
            reasons.append("Weekly loss limit reached.")
            veto = True
        if portfolio.drawdown_pct >= p.max_drawdown_pct:
            reasons.append("Maximum drawdown limit reached.")
            veto = True
        if portfolio.open_risk_pct >= p.max_open_risk_pct:
            reasons.append("Portfolio open-risk limit reached.")
            veto = True
        if portfolio.open_positions >= p.max_open_positions:
            reasons.append("Maximum number of open positions reached.")
            veto = True
        if portfolio.symbol_exposure.get(proposal.symbol, 0.0) >= p.max_symbol_exposure_pct:
            reasons.append("Symbol exposure limit reached.")
            veto = True
        if spread_points is not None and spread_points > p.max_spread_points:
            reasons.append(f"Spread {spread_points:.1f} exceeds allowed {p.max_spread_points:.1f} points.")
            veto = True

        requested = max(0.0, proposal.suggested_risk_pct)
        approved = min(requested, p.max_risk_per_trade_pct)
        remaining_portfolio_risk = max(0.0, p.max_open_risk_pct - portfolio.open_risk_pct)
        approved = min(approved, remaining_portfolio_risk)

        if approved <= 0:
            reasons.append("No risk budget remains.")
            veto = True

        if veto:
            return RiskVerdict(Decision.REJECT, 0.0, tuple(reasons), True)

        reasons.append(f"Approved risk {approved:.2f}% of equity.")
        return RiskVerdict(Decision.APPROVE, approved, tuple(reasons), False)
