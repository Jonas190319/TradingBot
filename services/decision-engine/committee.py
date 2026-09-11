from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List

from models import AnalystView, CommitteeDecision, Decision, Direction, Regime, TradeCandidate


DEFAULT_REGIME_WEIGHTS: Dict[Regime, Dict[str, float]] = {
    Regime.TREND: {"regime": 0.15, "technical": 0.25, "quant": 0.25, "macro": 0.10, "news": 0.05, "structure": 0.10, "execution": 0.10},
    Regime.RANGE: {"regime": 0.15, "technical": 0.20, "quant": 0.30, "macro": 0.05, "news": 0.05, "structure": 0.15, "execution": 0.10},
    Regime.BREAKOUT: {"regime": 0.15, "technical": 0.25, "quant": 0.25, "macro": 0.05, "news": 0.05, "structure": 0.10, "execution": 0.15},
    Regime.HIGH_VOL: {"regime": 0.15, "technical": 0.15, "quant": 0.25, "macro": 0.10, "news": 0.10, "structure": 0.10, "execution": 0.15},
    Regime.NEWS: {"regime": 0.10, "technical": 0.10, "quant": 0.20, "macro": 0.20, "news": 0.25, "structure": 0.05, "execution": 0.10},
}


def _agreement(view: AnalystView, candidate: TradeCandidate) -> float:
    if view.direction == Direction.NEUTRAL:
        return 0.5
    if view.direction == Direction.NO_TRADE:
        return 0.0
    return 1.0 if view.direction == candidate.direction else 0.0


@dataclass
class PortfolioCommittee:
    shadow_below: float = 70.0
    small_from: float = 70.0
    normal_from: float = 80.0
    strong_from: float = 90.0

    def evaluate(self, candidate: TradeCandidate, analyst_views: Iterable[AnalystView]) -> CommitteeDecision:
        views = list(analyst_views)
        weights = DEFAULT_REGIME_WEIGHTS.get(candidate.regime, DEFAULT_REGIME_WEIGHTS[Regime.TREND]).copy()

        score_parts: List[float] = [candidate.setup_score * 0.45]
        analyst_total = 0.0
        analyst_weight = 0.0
        for view in views:
            role_weight = weights.get(view.agent, 0.08)
            aligned = _agreement(view, candidate)
            calibrated = view.confidence * aligned
            analyst_total += calibrated * role_weight
            analyst_weight += role_weight

        analyst_score = analyst_total / analyst_weight if analyst_weight else 50.0
        rr_score = min(100.0, candidate.rr / 2.5 * 100.0)
        total = 0.45 * candidate.setup_score + 0.35 * analyst_score + 0.20 * rr_score

        hard_no_trade = any(v.direction == Direction.NO_TRADE and v.confidence >= 90 for v in views)
        if hard_no_trade:
            return CommitteeDecision(candidate.candidate_id, Decision.REJECT, total,
                                     "High-confidence NO_TRADE condition from analyst layer", 0.0, weights, views)
        if candidate.rr < 1.2:
            return CommitteeDecision(candidate.candidate_id, Decision.REJECT, total,
                                     f"Risk/reward too weak ({candidate.rr:.2f}R)", 0.0, weights, views)
        if total < self.shadow_below:
            return CommitteeDecision(candidate.candidate_id, Decision.SHADOW, total,
                                     "Candidate is tracked but not funded", 0.0, weights, views)
        if total < self.normal_from:
            return CommitteeDecision(candidate.candidate_id, Decision.APPROVE_REDUCED, total,
                                     "Positive edge, reduced sizing", 0.20, weights, views)
        if total < self.strong_from:
            return CommitteeDecision(candidate.candidate_id, Decision.APPROVE, total,
                                     "Qualified setup", 0.35, weights, views)
        return CommitteeDecision(candidate.candidate_id, Decision.APPROVE, total,
                                 "High-quality setup; risk remains capped", 0.50, weights, views)
