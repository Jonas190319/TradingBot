from __future__ import annotations

from datetime import timedelta

from .base import AgentContext, clamp
from .models import AgentSignal, Direction, utcnow


class MacroAgent:
    name = "macro"

    def analyze(self, context: AgentContext) -> AgentSignal:
        now = context.market.ts
        relevant = []
        for e in context.economic_events:
            if abs((e.ts - now).total_seconds()) <= timedelta(hours=4).total_seconds():
                relevant.append(e)

        if not relevant:
            return AgentSignal(utcnow(), context.market.symbol, self.name, Direction.NEUTRAL, 30, 10,
                               "No immediate macro catalyst", "No nearby economic release supplied.")

        surprise_sum = 0.0
        weight_sum = 0.0
        high_impact_pending = False
        details = []
        for e in relevant:
            weight = float(max(1, min(3, e.importance)))
            if e.actual is None or e.consensus is None:
                if e.importance >= 3 and e.ts >= now:
                    high_impact_pending = True
                continue
            denom = max(abs(e.consensus), abs(e.previous or 0.0), 1e-9)
            surprise = (e.actual - e.consensus) / denom
            surprise = clamp(surprise, -2.0, 2.0)
            surprise_sum += surprise * weight
            weight_sum += weight
            details.append({"title": e.title, "surprise": surprise, "importance": e.importance})

        if high_impact_pending:
            return AgentSignal(utcnow(), context.market.symbol, self.name, Direction.NO_TRADE, 85, 90,
                               "Wait for scheduled high-impact release", "A high-impact macro event is imminent.",
                               {"events": details})

        macro_score = surprise_sum / weight_sum if weight_sum else 0.0
        # Generic score: sign is not blindly mapped to every instrument. Pair-specific inversion belongs in symbol metadata later.
        if macro_score > 0.08:
            direction = Direction.LONG
        elif macro_score < -0.08:
            direction = Direction.SHORT
        else:
            direction = Direction.NEUTRAL
        conf = clamp(abs(macro_score) * 100 + 35, 0, 100)
        risk = clamp(max((e.importance for e in relevant), default=1) / 3 * 70, 0, 100)
        return AgentSignal(utcnow(), context.market.symbol, self.name, direction, conf, risk,
                           "Macro surprise evaluated", f"Normalized macro surprise score={macro_score:.2f}.",
                           {"macro_score": macro_score, "events": details})
