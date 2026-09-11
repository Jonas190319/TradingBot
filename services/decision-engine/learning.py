from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Tuple


@dataclass
class TradeOutcome:
    strategy: str
    symbol: str
    regime: str
    session: str
    direction: str
    realized_r: float
    mfe_r: float
    mae_r: float
    was_executed: bool
    committee_score: float
    setup_score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class LearningEngine:
    """Aggregates outcomes without changing live rules by itself."""

    def __init__(self) -> None:
        self.outcomes: List[TradeOutcome] = []

    def add(self, outcome: TradeOutcome) -> None:
        self.outcomes.append(outcome)

    @staticmethod
    def expectancy(outcomes: Iterable[TradeOutcome]) -> float:
        rows = list(outcomes)
        return sum(o.realized_r for o in rows) / len(rows) if rows else 0.0

    @staticmethod
    def profit_factor(outcomes: Iterable[TradeOutcome]) -> float:
        rows = list(outcomes)
        gross_profit = sum(max(0.0, o.realized_r) for o in rows)
        gross_loss = abs(sum(min(0.0, o.realized_r) for o in rows))
        return gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)

    def by_slice(self) -> Dict[Tuple[str, str, str, str], Dict[str, float]]:
        buckets: Dict[Tuple[str, str, str, str], List[TradeOutcome]] = defaultdict(list)
        for row in self.outcomes:
            buckets[(row.strategy, row.symbol, row.regime, row.session)].append(row)

        result: Dict[Tuple[str, str, str, str], Dict[str, float]] = {}
        for key, rows in buckets.items():
            wins = sum(1 for r in rows if r.realized_r > 0)
            avg_mfe = sum(r.mfe_r for r in rows) / len(rows)
            avg_mae = sum(r.mae_r for r in rows) / len(rows)
            avg_capture = sum((r.realized_r / r.mfe_r) if r.mfe_r > 0 else 0.0 for r in rows) / len(rows)
            result[key] = {
                "n": float(len(rows)),
                "hit_rate": wins / len(rows),
                "expectancy_r": self.expectancy(rows),
                "profit_factor": self.profit_factor(rows),
                "avg_mfe_r": avg_mfe,
                "avg_mae_r": avg_mae,
                "avg_capture_ratio": avg_capture,
            }
        return result

    def opportunity_audit(self) -> Dict[str, Any]:
        executed = [o for o in self.outcomes if o.was_executed]
        shadow = [o for o in self.outcomes if not o.was_executed]
        return {
            "executed_n": len(executed),
            "executed_expectancy_r": self.expectancy(executed),
            "executed_pf": self.profit_factor(executed),
            "shadow_n": len(shadow),
            "shadow_expectancy_r": self.expectancy(shadow),
            "shadow_pf": self.profit_factor(shadow),
            "filter_too_strict_flag": bool(len(shadow) >= 30 and self.expectancy(shadow) > self.expectancy(executed)),
        }

    def management_audit(self) -> Dict[str, Any]:
        executed = [o for o in self.outcomes if o.was_executed]
        if not executed:
            return {"n": 0}
        avg_mfe = sum(o.mfe_r for o in executed) / len(executed)
        avg_realized = sum(o.realized_r for o in executed) / len(executed)
        giveback = avg_mfe - avg_realized
        return {
            "n": len(executed),
            "avg_mfe_r": avg_mfe,
            "avg_realized_r": avg_realized,
            "avg_giveback_r": giveback,
            "exit_review_flag": bool(giveback > 0.6),
        }
