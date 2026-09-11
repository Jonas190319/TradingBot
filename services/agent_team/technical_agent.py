from __future__ import annotations

from .base import AgentContext, clamp, mean, stdev
from .models import AgentSignal, Direction, utcnow


class TechnicalAgent:
    name = "technical"

    def analyze(self, context: AgentContext) -> AgentSignal:
        bars = list(context.market.bars)
        if len(bars) < 30:
            return AgentSignal(utcnow(), context.market.symbol, self.name, Direction.NO_TRADE, 20, 35,
                               "Insufficient technical history", f"Need at least 30 bars; got {len(bars)}.")

        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        fast = mean(closes[-10:])
        slow = mean(closes[-30:])
        returns = [(closes[i] / closes[i - 1] - 1.0) for i in range(1, len(closes)) if closes[i - 1]]
        vol = stdev(returns[-30:])
        recent_high = max(highs[-20:-1])
        recent_low = min(lows[-20:-1])
        last = closes[-1]
        trend_strength = abs(fast - slow) / max(abs(slow), 1e-9)
        breakout_up = last > recent_high
        breakout_down = last < recent_low
        momentum = (last / closes[-6] - 1.0) if closes[-6] else 0.0

        if breakout_up and momentum > 0:
            direction = Direction.LONG
            setup = "breakout"
        elif breakout_down and momentum < 0:
            direction = Direction.SHORT
            setup = "breakout"
        elif fast > slow and momentum > 0:
            direction = Direction.LONG
            setup = "trend"
        elif fast < slow and momentum < 0:
            direction = Direction.SHORT
            setup = "trend"
        else:
            direction = Direction.NEUTRAL
            setup = "mixed"

        confidence = clamp(40 + trend_strength * 12000 + abs(momentum) * 4000, 0, 95)
        risk = clamp(vol * 25000, 5, 95)
        if setup == "mixed" and confidence < 60:
            direction = Direction.NO_TRADE

        return AgentSignal(
            utcnow(), context.market.symbol, self.name, direction, confidence, risk,
            f"Technical setup: {setup}",
            f"MA10={fast:.5f}, MA30={slow:.5f}, momentum={momentum:.4%}, volatility={vol:.4%}.",
            {
                "setup": setup,
                "ma_fast": fast,
                "ma_slow": slow,
                "momentum": momentum,
                "volatility": vol,
                "recent_high": recent_high,
                "recent_low": recent_low,
                "breakout_up": breakout_up,
                "breakout_down": breakout_down,
            },
        )
