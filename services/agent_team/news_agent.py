from __future__ import annotations

from .base import AgentContext, clamp
from .event_mode import EventMode
from .models import AgentSignal, Direction, utcnow


class NewsAgent:
    name = "news"

    def __init__(self) -> None:
        self.event_mode = EventMode()

    def analyze(self, context: AgentContext) -> AgentSignal:
        event = self.event_mode.assess(context.market, context.economic_events)
        if event.active:
            return AgentSignal(
                utcnow(), context.market.symbol, self.name, event.direction,
                event.confidence, event.risk_score,
                "Observe scheduled macro event; require market confirmation",
                event.reason,
                {"event_mode": True, "phase": event.phase, "event_key": event.event_key,
                 "importance": event.importance, "relevance": event.relevance,
                 "surprise": event.surprise, **event.payload},
            )

        relevant = [n for n in context.news if not n.symbols or context.market.symbol in n.symbols]
        if not relevant:
            return AgentSignal(utcnow(), context.market.symbol, self.name, Direction.NEUTRAL, 35, 15,
                               "No material headline signal", "No relevant headlines supplied.")

        weighted = 0.0
        severity = 0.0
        for item in relevant[-20:]:
            w = max(0.1, item.severity)
            weighted += item.sentiment * w
            severity += w
        score = weighted / severity if severity else 0.0
        conf = clamp(abs(score) * 100 + min(25, severity * 8), 0, 100)
        risk = clamp(max((n.severity for n in relevant), default=0) * 100, 0, 100)

        if risk >= 85 and abs(score) < 0.25:
            direction = Direction.NO_TRADE
            recommendation = "Wait for headline uncertainty to clear"
        elif score > 0.15:
            direction = Direction.LONG
            recommendation = "Headline flow supports upside"
        elif score < -0.15:
            direction = Direction.SHORT
            recommendation = "Headline flow supports downside"
        else:
            direction = Direction.NEUTRAL
            recommendation = "Headlines are mixed"

        return AgentSignal(
            utcnow(), context.market.symbol, self.name, direction, conf, risk,
            recommendation,
            f"Aggregated {len(relevant)} relevant headlines; sentiment={score:.2f}, max severity={risk:.0f}/100.",
            {"event_mode": False, "headline_count": len(relevant), "sentiment_score": score, "max_severity": risk},
        )
