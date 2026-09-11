from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from models import CommitteeDecision, Decision, TradeCandidate


@dataclass
class PortfolioState:
    equity: float
    daily_pnl_pct: float
    weekly_pnl_pct: float
    drawdown_pct: float
    open_risk_pct: float
    correlated_risk_pct: float
    spread_multiple: float = 1.0
    slippage_multiple: float = 1.0


@dataclass
class RiskApproval:
    approved: bool
    risk_pct: float
    risk_amount: float
    position_size_units: float
    reason: str


@dataclass
class RiskManager:
    max_risk_per_trade_pct: float = 0.50
    max_daily_loss_pct: float = 1.50
    max_weekly_loss_pct: float = 3.00
    max_drawdown_pct: float = 8.00
    max_open_risk_pct: float = 1.50
    max_correlated_risk_pct: float = 0.80
    max_spread_multiple: float = 2.5
    max_slippage_multiple: float = 2.0

    def assess(self, candidate: TradeCandidate, committee: CommitteeDecision, state: PortfolioState) -> RiskApproval:
        if committee.decision in {Decision.REJECT, Decision.SHADOW}:
            return RiskApproval(False, 0.0, 0.0, 0.0, f"Committee decision: {committee.decision.value}")
        if state.daily_pnl_pct <= -self.max_daily_loss_pct:
            return RiskApproval(False, 0.0, 0.0, 0.0, "Daily loss limit reached")
        if state.weekly_pnl_pct <= -self.max_weekly_loss_pct:
            return RiskApproval(False, 0.0, 0.0, 0.0, "Weekly loss limit reached")
        if state.drawdown_pct >= self.max_drawdown_pct:
            return RiskApproval(False, 0.0, 0.0, 0.0, "Drawdown kill switch")
        if state.open_risk_pct >= self.max_open_risk_pct:
            return RiskApproval(False, 0.0, 0.0, 0.0, "Open portfolio risk cap reached")
        if state.correlated_risk_pct >= self.max_correlated_risk_pct:
            return RiskApproval(False, 0.0, 0.0, 0.0, "Correlated exposure cap reached")
        if state.spread_multiple > self.max_spread_multiple:
            return RiskApproval(False, 0.0, 0.0, 0.0, "Spread abnormal")
        if state.slippage_multiple > self.max_slippage_multiple:
            return RiskApproval(False, 0.0, 0.0, 0.0, "Slippage abnormal")

        requested = min(committee.approved_risk_pct, self.max_risk_per_trade_pct)
        remaining_open = max(0.0, self.max_open_risk_pct - state.open_risk_pct)
        remaining_corr = max(0.0, self.max_correlated_risk_pct - state.correlated_risk_pct)
        risk_pct = min(requested, remaining_open, remaining_corr)
        if risk_pct <= 0:
            return RiskApproval(False, 0.0, 0.0, 0.0, "No remaining risk budget")

        risk_amount = state.equity * (risk_pct / 100.0)
        stop_distance = candidate.stop_distance
        if stop_distance <= 0:
            return RiskApproval(False, 0.0, 0.0, 0.0, "Invalid stop distance")

        # Units are normalized risk units until broker-specific tick-value conversion is attached.
        position_size_units = risk_amount / stop_distance
        reason = "Approved"
        if risk_pct < requested:
            reason = "Approved with reduced size due to portfolio/correlation budget"
        return RiskApproval(True, risk_pct, risk_amount, position_size_units, reason)
