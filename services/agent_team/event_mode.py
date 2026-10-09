from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .base import clamp
from .models import Direction, EconomicEvent, MarketSnapshot


@dataclass(frozen=True)
class EventReaction:
    event_key: str
    symbol: str
    event_ts: datetime
    observed_ts: datetime
    seconds_after: float
    mid: float
    spread_points: float | None
    return_bps: float | None


@dataclass(frozen=True)
class EventAssessment:
    active: bool
    phase: str
    event_key: str | None
    importance: int
    relevance: float
    surprise: float | None
    direction: Direction
    confidence: float
    risk_score: float
    reason: str
    payload: dict[str, object] = field(default_factory=dict)


class EventMode:
    """Fast deterministic event layer for scheduled macro releases.

    No web/LLM work belongs on this path. A feed adapter supplies EconomicEvent
    objects; this layer maps them to the traded symbol, measures standardized
    surprise and records reaction checkpoints for later learning.
    """

    PRE_EVENT_SECONDS = 300
    POST_EVENT_SECONDS = 4 * 60 * 60
    CHECKPOINTS = (1, 5, 15, 30, 60, 300, 900, 3600, 14400)

    def assess(self, market: MarketSnapshot, events: Iterable[EconomicEvent]) -> EventAssessment:
        relevant = [e for e in events if self._relevance(market.symbol, e.currency) > 0]
        if not relevant:
            return EventAssessment(False, "normal", None, 0, 0, None, Direction.NEUTRAL, 0, 0,
                                   "No relevant scheduled macro event")

        now = market.ts.astimezone(timezone.utc)
        event = min(relevant, key=lambda e: abs((e.ts.astimezone(timezone.utc) - now).total_seconds()))
        delta = (now - event.ts.astimezone(timezone.utc)).total_seconds()
        relevance = self._relevance(market.symbol, event.currency)
        key = self.event_key(event)

        if delta < -self.PRE_EVENT_SECONDS or delta > self.POST_EVENT_SECONDS:
            return EventAssessment(False, "normal", key, event.importance, relevance, None,
                                   Direction.NEUTRAL, 0, 0, "Relevant event outside event window")
        if delta < 0:
            risk = clamp(event.importance / 3 * 100 * relevance, 0, 100)
            return EventAssessment(True, "pre_news", key, event.importance, relevance, None,
                                   Direction.NO_TRADE if event.importance >= 3 else Direction.NEUTRAL,
                                   90 if event.importance >= 3 else 60, risk,
                                   f"Scheduled {event.title} in {abs(delta):.0f}s; prepare fast path",
                                   {"seconds_to_event": abs(delta), "currency": event.currency})

        surprise = self._surprise(event)
        if event.actual is None:
            return EventAssessment(True, "await_actual", key, event.importance, relevance, None,
                                   Direction.NO_TRADE, 95, 95,
                                   "Release time reached but actual value is not available yet")

        # Direction is a macro impulse, not an execution instruction. For FX,
        # positive currency surprise supports base currency and weighs on quote.
        impulse = self._event_impulse(event, surprise)
        sign = self._symbol_currency_sign(market.symbol, event.currency)
        directional = impulse * sign
        direction = Direction.LONG if directional > 0.10 else Direction.SHORT if directional < -0.10 else Direction.NEUTRAL
        confidence = clamp(abs(directional) * 70 + event.importance * 8, 0, 100)
        risk = clamp(55 + event.importance * 12 - min(max(delta, 0) / 60, 25), 0, 100)
        return EventAssessment(True, "post_news", key, event.importance, relevance, surprise,
                               direction, confidence, risk,
                               "Macro impulse classified; confirm with observed price/structure before execution",
                               {"seconds_after": delta, "currency": event.currency,
                                "actual": event.actual, "consensus": event.consensus,
                                "previous": event.previous, "unit": event.unit})

    @staticmethod
    def event_key(event: EconomicEvent) -> str:
        ts = event.ts.astimezone(timezone.utc).isoformat()
        return f"{event.currency.upper()}:{event.title}:{ts}"

    @staticmethod
    def _surprise(event: EconomicEvent) -> float | None:
        if event.actual is None or event.consensus is None:
            return None
        scale = abs(event.consensus) if abs(event.consensus) > 1e-9 else max(abs(event.previous or 0), 1.0)
        return (event.actual - event.consensus) / scale

    @staticmethod
    def _event_impulse(event: EconomicEvent, surprise: float | None) -> float:
        if surprise is None:
            return 0.0
        title = event.title.lower()
        # Higher inflation/activity is usually currency-positive through rates;
        # higher unemployment is usually currency-negative. This is only a prior.
        inverse = any(x in title for x in ("unemployment", "jobless", "claims"))
        return clamp((-surprise if inverse else surprise) * (event.importance / 3), -1, 1)

    @staticmethod
    def _relevance(symbol: str, currency: str) -> float:
        s, c = symbol.upper(), currency.upper()
        if c in s:
            return 1.0
        if c == "USD" and any(x in s for x in ("NAS100", "US100", "USTEC", "US500", "SPX500", "US30", "XAU", "GOLD")):
            return 0.9
        if c == "EUR" and any(x in s for x in ("GER40", "DAX40", "DE40")):
            return 0.8
        return 0.0

    @staticmethod
    def _symbol_currency_sign(symbol: str, currency: str) -> float:
        s, c = symbol.upper(), currency.upper()
        if len(s) >= 6 and s[:3] == c:
            return 1.0
        if len(s) >= 6 and s[3:6] == c:
            return -1.0
        # Cross-asset sign intentionally neutral until empirically calibrated.
        return 0.0


class ReactionTracker:
    """Collects fixed post-release observations without blocking execution."""

    def __init__(self) -> None:
        self._anchors: dict[tuple[str, str], float] = {}
        self._seen: set[tuple[str, str, int]] = set()

    def anchor(self, event: EconomicEvent, market: MarketSnapshot) -> None:
        self._anchors[(EventMode.event_key(event), market.symbol)] = market.mid

    def observe(self, event: EconomicEvent, market: MarketSnapshot, tolerance_seconds: float = 1.5) -> tuple[EventReaction, ...]:
        key = EventMode.event_key(event)
        anchor = self._anchors.get((key, market.symbol))
        elapsed = (market.ts.astimezone(timezone.utc) - event.ts.astimezone(timezone.utc)).total_seconds()
        out = []
        for checkpoint in EventMode.CHECKPOINTS:
            marker = (key, market.symbol, checkpoint)
            if marker in self._seen or abs(elapsed - checkpoint) > tolerance_seconds:
                continue
            ret = ((market.mid / anchor) - 1) * 10000 if anchor and anchor > 0 else None
            out.append(EventReaction(key, market.symbol, event.ts, market.ts, elapsed,
                                     market.mid, market.spread_points, ret))
            self._seen.add(marker)
        return tuple(out)
