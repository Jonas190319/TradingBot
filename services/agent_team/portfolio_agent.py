from __future__ import annotations

from collections import Counter

from .base import clamp
from .models import AgentSignal, Direction, Regime, TradeProposal, utcnow


class PortfolioManager:
    """Combines specialist opinions. It never executes orders."""

    name = "portfolio"
    weights = {
        "news": 0.15,
        "macro": 0.15,
        "technical": 0.25,
        "quant": 0.20,
        "regime": 0.25,
    }

    def propose(self, symbol: str, signals: list[AgentSignal], min_quality: float = 80.0) -> TradeProposal | None:
        if not signals:
            return None

        by_agent = {s.agent_type: s for s in signals}
        regime_signal = by_agent.get("regime")
        regime_name = (regime_signal.payload.get("regime") if regime_signal else None) or Regime.UNKNOWN.value
        try:
            regime = Regime(regime_name)
        except ValueError:
            regime = Regime.UNKNOWN

        if any(s.direction == Direction.NO_TRADE and s.confidence >= 80 for s in signals):
            return None
        if regime in (Regime.CHAOS, Regime.NEWS):
            return None

        directional = [s for s in signals if s.agent_type != "regime" and s.direction in (Direction.LONG, Direction.SHORT)]
        if len(directional) < 2:
            return None

        votes = Counter(s.direction for s in directional)
        winner, count = votes.most_common(1)[0]
        if count / len(directional) < 0.60:
            return None

        agreement = count / len(directional)
        weighted_conf = 0.0
        total_w = 0.0
        weighted_risk = 0.0
        components: dict[str, float] = {}
        for s in signals:
            w = self.weights.get(s.agent_type, 0.0)
            if w <= 0:
                continue
            alignment = 1.0 if s.direction in (winner, Direction.NEUTRAL) else 0.35
            contribution = s.confidence * w * alignment
            weighted_conf += contribution
            weighted_risk += s.risk_score * w
            total_w += w
            components[s.agent_type] = round(contribution, 2)

        confidence = weighted_conf / total_w if total_w else 0.0
        risk = weighted_risk / total_w if total_w else 100.0
        regime_bonus = {Regime.TREND: 8, Regime.BREAKOUT: 5, Regime.RANGE: -8, Regime.UNKNOWN: -12}.get(regime, 0)
        quality = clamp(confidence * 0.70 + agreement * 100 * 0.25 + regime_bonus - risk * 0.10, 0, 100)
        if quality < min_quality:
            return None

        strategy = "trend_following" if regime == Regime.TREND else "breakout" if regime == Regime.BREAKOUT else "selective"
        risk_pct = 0.25 if quality < 88 else 0.35 if quality < 94 else 0.50
        return TradeProposal(
            ts=utcnow(), symbol=symbol, direction=winner, quality_score=quality, confidence=confidence,
            regime=regime, strategy=strategy, stop_distance_points=None, target_distance_points=None,
            suggested_risk_pct=risk_pct,
            rationale=f"{count}/{len(directional)} directional specialists agree; quality={quality:.1f}/100.",
            components=components,
        )
