from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from committee import PortfolioCommittee
from models import AnalystView, CommitteeDecision, MarketSnapshot, Regime, TradeCandidate
from pretrade import PreTradeRecorder
from risk_manager import PortfolioState, RiskApproval, RiskManager
from strategists import CORE_STRATEGISTS


@dataclass
class CandidateResult:
    candidate: TradeCandidate
    committee: CommitteeDecision
    risk: RiskApproval
    pretrade_summary: Dict[str, object]


class ExpertTeamOrchestrator:
    """Coordinates strategists, committee, pre-trade recording and risk.

    It does not send broker orders. Execution stays a separate boundary so the
    decision system can be tested in replay, shadow and demo modes unchanged.
    """

    def __init__(self) -> None:
        self.strategists = CORE_STRATEGISTS
        self.pretrade = PreTradeRecorder()
        self.committee = PortfolioCommittee()
        self.risk = RiskManager()

    def evaluate_market(
        self,
        snapshot: MarketSnapshot,
        regime: Regime,
        analyst_views: Iterable[AnalystView],
        portfolio_state: PortfolioState,
    ) -> List[CandidateResult]:
        self.pretrade.observe(snapshot)
        results: List[CandidateResult] = []
        views = list(analyst_views)

        for strategist in self.strategists:
            candidate = strategist.evaluate(snapshot, regime)
            if candidate is None:
                continue

            self.pretrade.record_candidate(
                candidate_id=candidate.candidate_id,
                strategy=candidate.strategy,
                stage="qualified_candidate",
                score=candidate.setup_score,
                snapshot=snapshot,
                notes={
                    "direction": candidate.direction.value,
                    "entry": candidate.entry,
                    "sl": candidate.stop_loss,
                    "tp1": candidate.take_profit_1,
                    "tp2": candidate.take_profit_2,
                    "rr": candidate.rr,
                    "regime": candidate.regime.value,
                },
            )

            committee_decision = self.committee.evaluate(candidate, views)
            self.pretrade.record_candidate(
                candidate_id=candidate.candidate_id,
                strategy=candidate.strategy,
                stage=f"committee_{committee_decision.decision.value}",
                score=committee_decision.score,
                snapshot=snapshot,
                notes={"rationale": committee_decision.rationale},
            )

            risk_approval = self.risk.assess(candidate, committee_decision, portfolio_state)
            self.pretrade.record_candidate(
                candidate_id=candidate.candidate_id,
                strategy=candidate.strategy,
                stage="risk_approved" if risk_approval.approved else "risk_rejected",
                score=committee_decision.score,
                snapshot=snapshot,
                notes={
                    "risk_pct": risk_approval.risk_pct,
                    "risk_amount": risk_approval.risk_amount,
                    "reason": risk_approval.reason,
                },
            )

            results.append(
                CandidateResult(
                    candidate=candidate,
                    committee=committee_decision,
                    risk=risk_approval,
                    pretrade_summary=self.pretrade.summarize(candidate.candidate_id),
                )
            )

        return sorted(results, key=lambda r: r.committee.score, reverse=True)
