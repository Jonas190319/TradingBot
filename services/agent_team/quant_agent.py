from __future__ import annotations

from .base import AgentContext, clamp, mean, stdev
from .models import AgentSignal, Direction, utcnow


class QuantAgent:
    name = "quant"

    def analyze(self, context: AgentContext) -> AgentSignal:
        bars = list(context.market.bars)
        if len(bars) < 50:
            return AgentSignal(utcnow(), context.market.symbol, self.name, Direction.NO_TRADE, 20, 30,
                               "Insufficient sample for quant estimate", f"Need at least 50 bars; got {len(bars)}.")

        closes = [b.close for b in bars]
        rets = [(closes[i] / closes[i - 1] - 1.0) for i in range(1, len(closes)) if closes[i - 1]]
        short = rets[-10:]
        long = rets[-40:]
        short_mean = mean(short)
        long_mean = mean(long)
        sigma = stdev(long)
        z = 0.0 if sigma == 0 else (short_mean - long_mean) / (sigma / max(len(short), 1) ** 0.5)

        # Momentum persistence estimate over recent returns.
        signs = [1 if r > 0 else -1 if r < 0 else 0 for r in rets[-30:]]
        same_direction = 0
        pairs = 0
        for a, b in zip(signs, signs[1:]):
            if a and b:
                pairs += 1
                same_direction += int(a == b)
        persistence = same_direction / pairs if pairs else 0.5

        score = clamp(z / 3.0, -1.0, 1.0)
        if score > 0.15:
            direction = Direction.LONG
        elif score < -0.15:
            direction = Direction.SHORT
        else:
            direction = Direction.NEUTRAL

        confidence = clamp(abs(score) * 70 + abs(persistence - 0.5) * 80 + 25, 0, 90)
        risk = clamp(sigma * 30000, 5, 90)
        if direction == Direction.NEUTRAL and confidence < 55:
            direction = Direction.NO_TRADE

        return AgentSignal(
            utcnow(), context.market.symbol, self.name, direction, confidence, risk,
            "Statistical edge estimate",
            f"z={z:.2f}, persistence={persistence:.2f}, recent mean return={short_mean:.5%}.",
            {"z_score": z, "persistence": persistence, "short_mean_return": short_mean,
             "long_mean_return": long_mean, "volatility": sigma},
        )
