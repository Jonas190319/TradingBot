from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Protocol, Sequence


class CandidateLike(Protocol):
    candidate: object
    committee: object
    risk: object


@dataclass(frozen=True)
class OpenExposure:
    symbol: str
    strategy: str
    risk_pct: float


@dataclass(frozen=True)
class AllocationDecision:
    candidate_id: str
    symbol: str
    strategy: str
    selected: bool
    rank_score: float
    funded_risk_pct: float
    reason: str


@dataclass(frozen=True)
class AllocationPlan:
    selected: tuple[CandidateLike, ...]
    decisions: tuple[AllocationDecision, ...]
    total_open_positions: int
    total_risk_pct: float


@dataclass
class PortfolioAllocator:
    """Ranks approved candidates and funds only the best portfolio combination.

    This layer runs after committee + per-trade risk checks and before execution.
    It does not close an existing trade to make room for a new signal.
    """

    max_open_positions: int = 5
    max_opening_range_positions: int = 5
    max_total_open_risk_pct: float = 1.50
    min_rank_score: float = 70.0
    max_same_factor_positions: int = 2
    factor_penalty: float = 8.0

    def allocate(
        self,
        candidates: Iterable[CandidateLike],
        open_exposures: Sequence[OpenExposure] = (),
    ) -> AllocationPlan:
        approved = [c for c in candidates if bool(getattr(c.risk, "approved", False))]
        open_count = len(open_exposures)
        open_risk = sum(max(0.0, x.risk_pct) for x in open_exposures)
        strategy_counts: dict[str, int] = {}
        factor_counts: dict[str, int] = {}

        for exposure in open_exposures:
            strategy_counts[exposure.strategy] = strategy_counts.get(exposure.strategy, 0) + 1
            for factor in self._factors(exposure.symbol):
                factor_counts[factor] = factor_counts.get(factor, 0) + 1

        ranked = sorted(approved, key=lambda c: self._rank_score(c, factor_counts), reverse=True)
        selected: List[CandidateLike] = []
        decisions: List[AllocationDecision] = []
        running_risk = open_risk
        running_count = open_count

        for result in ranked:
            candidate = result.candidate
            symbol = str(getattr(candidate, "symbol"))
            strategy = str(getattr(candidate, "strategy"))
            candidate_id = str(getattr(candidate, "candidate_id"))
            requested_risk = max(0.0, float(getattr(result.risk, "risk_pct", 0.0)))
            rank_score = self._rank_score(result, factor_counts)

            if rank_score < self.min_rank_score:
                decisions.append(AllocationDecision(candidate_id, symbol, strategy, False, rank_score, 0.0,
                                                   "Portfolio rank below funding threshold"))
                continue
            if running_count >= self.max_open_positions:
                decisions.append(AllocationDecision(candidate_id, symbol, strategy, False, rank_score, 0.0,
                                                   "Maximum open positions reached; candidate remains shadow"))
                continue
            if strategy == "opening_range" and strategy_counts.get(strategy, 0) >= self.max_opening_range_positions:
                decisions.append(AllocationDecision(candidate_id, symbol, strategy, False, rank_score, 0.0,
                                                   "Opening-range position cap reached"))
                continue

            factors = self._factors(symbol)
            if factors and any(factor_counts.get(f, 0) >= self.max_same_factor_positions for f in factors):
                decisions.append(AllocationDecision(candidate_id, symbol, strategy, False, rank_score, 0.0,
                                                   "Correlated factor exposure cap reached"))
                continue

            remaining_risk = max(0.0, self.max_total_open_risk_pct - running_risk)
            funded = min(requested_risk, remaining_risk)
            if funded <= 0:
                decisions.append(AllocationDecision(candidate_id, symbol, strategy, False, rank_score, 0.0,
                                                   "No remaining portfolio risk budget"))
                continue

            selected.append(result)
            decisions.append(AllocationDecision(candidate_id, symbol, strategy, True, rank_score, funded,
                                               "Selected as one of the best currently fundable candidates"))
            running_count += 1
            running_risk += funded
            strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
            for factor in factors:
                factor_counts[factor] = factor_counts.get(factor, 0) + 1

        selected_ids = {str(getattr(r.candidate, "candidate_id")) for r in selected}
        for result in candidates:
            cid = str(getattr(result.candidate, "candidate_id"))
            if cid in selected_ids or any(d.candidate_id == cid for d in decisions):
                continue
            decisions.append(AllocationDecision(
                cid,
                str(getattr(result.candidate, "symbol")),
                str(getattr(result.candidate, "strategy")),
                False,
                self._rank_score(result, factor_counts),
                0.0,
                "Not individually risk-approved",
            ))

        return AllocationPlan(tuple(selected), tuple(decisions), running_count, running_risk)

    def _rank_score(self, result: CandidateLike, existing_factors: dict[str, int]) -> float:
        candidate = result.candidate
        committee_score = float(getattr(result.committee, "score", 0.0))
        setup_score = float(getattr(candidate, "setup_score", 0.0))
        rr = max(0.0, float(getattr(candidate, "rr", 0.0)))
        rr_score = min(100.0, rr / 2.5 * 100.0)
        risk_pct = max(0.0, float(getattr(result.risk, "risk_pct", 0.0)))
        risk_efficiency = max(0.0, 100.0 - risk_pct * 40.0)
        overlap = sum(existing_factors.get(f, 0) for f in self._factors(str(getattr(candidate, "symbol"))))
        return max(0.0, min(100.0,
            0.45 * committee_score + 0.25 * setup_score + 0.20 * rr_score + 0.10 * risk_efficiency
            - overlap * self.factor_penalty
        ))

    @staticmethod
    def _factors(symbol: str) -> set[str]:
        s = symbol.upper().replace(".", "").replace("_", "")
        factors: set[str] = set()
        for ccy in ("EUR", "USD", "JPY", "GBP", "CHF", "AUD", "NZD", "CAD"):
            if ccy in s:
                factors.add(f"ccy:{ccy}")
        if any(x in s for x in ("NAS100", "USTEC", "US100", "US500", "SPX500", "US30", "DJ30")):
            factors.add("index:US")
        if any(x in s for x in ("GER40", "DAX40", "DE40")):
            factors.add("index:DE")
        if any(x in s for x in ("XAU", "GOLD")):
            factors.add("commodity:GOLD")
        if any(x in s for x in ("XAG", "SILVER")):
            factors.add("commodity:SILVER")
        if any(x in s for x in ("WTI", "USOIL", "BRENT", "UKOIL")):
            factors.add("commodity:OIL")
        return factors
