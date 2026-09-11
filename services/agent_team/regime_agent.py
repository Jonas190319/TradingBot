from __future__ import annotations

from datetime import timedelta

from .base import AgentContext, clamp, mean, stdev
from .models import AgentSignal, Direction, Regime, utcnow


class RegimeAgent:
    name = "regime"

    def analyze(self, context: AgentContext) -> AgentSignal:
        bars = list(context.market.bars)
        if len(bars) < 30:
            return AgentSignal(utcnow(), context.market.symbol, self.name, Direction.NO_TRADE, 25, 50,
                               "Regime unknown", "Insufficient bars to classify regime.",
                               {"regime": Regime.UNKNOWN.value})

        now = context.market.ts
        imminent_high_impact = any(
            e.importance >= 3 and timedelta(minutes=-15) <= (e.ts - now) <= timedelta(minutes=30)
            for e in context.economic_events
        )
        if imminent_high_impact:
            return AgentSignal(utcnow(), context.market.symbol, self.name, Direction.NO_TRADE, 95, 90,
                               "NEWS regime", "High-impact release is inside the event lock window.",
                               {"regime": Regime.NEWS.value})

        closes = [b.close for b in bars]
        ranges = [(b.high - b.low) / max(abs(b.close), 1e-9) for b in bars]
        rets = [(closes[i] / closes[i - 1] - 1.0) for i in range(1, len(closes)) if closes[i - 1]]
        vol_short = stdev(rets[-10:])
        vol_long = stdev(rets[-30:])
        avg_range = mean(ranges[-20:])
        fast = mean(closes[-10:])
        slow = mean(closes[-30:])
        trend = abs(fast - slow) / max(abs(slow), 1e-9)
        compression = avg_range < mean(ranges[-30:]) * 0.75 if len(ranges) >= 30 else False
        explosion = vol_long > 0 and vol_short > vol_long * 1.8

        if explosion:
            regime = Regime.CHAOS
            confidence = 85
            risk = 95
            direction = Direction.NO_TRADE
        elif compression:
            regime = Regime.BREAKOUT
            confidence = 70
            risk = 55
            direction = Direction.NEUTRAL
        elif trend > max(vol_long * 1.4, 0.0003):
            regime = Regime.TREND
            confidence = clamp(55 + trend * 10000, 0, 90)
            risk = clamp(vol_long * 25000, 10, 75)
            direction = Direction.NEUTRAL
        else:
            regime = Regime.RANGE
            confidence = 65
            risk = clamp(vol_long * 20000, 10, 65)
            direction = Direction.NEUTRAL

        return AgentSignal(
            utcnow(), context.market.symbol, self.name, direction, confidence, risk,
            f"Regime: {regime.value}",
            f"trend={trend:.4%}, vol_short={vol_short:.4%}, vol_long={vol_long:.4%}, compression={compression}.",
            {"regime": regime.value, "trend_strength": trend, "vol_short": vol_short,
             "vol_long": vol_long, "compression": compression},
        )
