from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class TradeRecord:
    strategy: str
    symbol: str
    regime: str
    session: str
    pnl_r: float
    slippage_points: float = 0.0
    quality_score: float = 0.0


@dataclass(frozen=True)
class Recommendation:
    title: str
    rationale: str
    evidence_count: int
    expected_effect: str
    requires_demo_validation: bool = True


class ImprovementAgent:
    """Research-only auditor. It never changes live parameters by itself."""

    name = "improvement"

    def analyze(self, trades: Iterable[TradeRecord]) -> list[Recommendation]:
        rows = list(trades)
        recommendations: list[Recommendation] = []
        if len(rows) < 20:
            return [Recommendation(
                "Collect more evidence before changing strategy",
                f"Only {len(rows)} completed trades are available; that sample is too small for robust changes.",
                len(rows),
                "Avoids overfitting and premature live changes.",
            )]

        by_strategy: dict[str, list[TradeRecord]] = {}
        by_symbol: dict[str, list[TradeRecord]] = {}
        by_session: dict[str, list[TradeRecord]] = {}
        for t in rows:
            by_strategy.setdefault(t.strategy, []).append(t)
            by_symbol.setdefault(t.symbol, []).append(t)
            by_session.setdefault(t.session or "unknown", []).append(t)

        def pf(sample: list[TradeRecord]) -> float:
            gains = sum(max(0.0, x.pnl_r) for x in sample)
            losses = abs(sum(min(0.0, x.pnl_r) for x in sample))
            return gains / losses if losses > 0 else float("inf")

        for name, sample in sorted(by_strategy.items()):
            if len(sample) >= 15 and pf(sample) < 1.0:
                recommendations.append(Recommendation(
                    f"Review or disable strategy: {name}",
                    f"Profit factor is {pf(sample):.2f} across {len(sample)} trades.",
                    len(sample),
                    "Potentially reduce drawdown; validate with backtest and four-week demo forward test.",
                ))

        for symbol, sample in sorted(by_symbol.items()):
            if len(sample) >= 15 and pf(sample) < 0.9:
                recommendations.append(Recommendation(
                    f"Reduce exposure to {symbol}",
                    f"{symbol} profit factor is {pf(sample):.2f} across {len(sample)} trades.",
                    len(sample),
                    "Remove a statistically weak market until a better regime filter is found.",
                ))

        for session, sample in sorted(by_session.items()):
            expectancy = sum(x.pnl_r for x in sample) / len(sample)
            if len(sample) >= 15 and expectancy < -0.05:
                recommendations.append(Recommendation(
                    f"Block or tighten session: {session}",
                    f"Average expectancy is {expectancy:.2f}R over {len(sample)} trades.",
                    len(sample),
                    "Avoid a repeatedly negative trading window.",
                ))

        high_slip = [t for t in rows if t.slippage_points > 20]
        if len(high_slip) >= max(5, int(len(rows) * 0.15)):
            recommendations.append(Recommendation(
                "Tighten execution/slippage filter",
                f"{len(high_slip)} of {len(rows)} trades exceeded 20 points of slippage.",
                len(high_slip),
                "Improve realized execution quality and reduce hidden transaction cost.",
            ))

        if not recommendations:
            recommendations.append(Recommendation(
                "Keep current strategy version unchanged",
                "No sufficiently supported degradation signal was found in the current sample.",
                len(rows),
                "Preserves a stable baseline and avoids unnecessary parameter churn.",
            ))
        return recommendations
