from __future__ import annotations

from dataclasses import dataclass

from .base import AgentContext
from .execution_agent import ExecutionAgent, ExecutionIntent, ExecutionPolicy
from .macro_agent import MacroAgent
from .models import AgentSignal, PortfolioState, RiskVerdict, TeamDecision, utcnow
from .news_agent import NewsAgent
from .portfolio_agent import PortfolioManager
from .quant_agent import QuantAgent
from .regime_agent import RegimeAgent
from .risk_manager import RiskManager, RiskPolicy
from .technical_agent import TechnicalAgent


@dataclass(frozen=True)
class TeamRunResult:
    signals: tuple[AgentSignal, ...]
    decision: TeamDecision
    execution: ExecutionIntent


class ExpertTeam:
    """Deterministic orchestration layer for the trading expert team.

    Specialist agents independently produce standardized signals. The PortfolioManager
    combines them. The RiskManager is independent and can veto. The ExecutionAgent is
    the final gate and is broker-agnostic until integration is explicitly added.
    """

    def __init__(
        self,
        risk_policy: RiskPolicy | None = None,
        execution_policy: ExecutionPolicy | None = None,
        min_quality: float = 80.0,
    ) -> None:
        self.specialists = (
            NewsAgent(),
            MacroAgent(),
            TechnicalAgent(),
            QuantAgent(),
            RegimeAgent(),
        )
        self.portfolio_manager = PortfolioManager()
        self.risk_manager = RiskManager(risk_policy)
        self.execution_agent = ExecutionAgent(execution_policy)
        self.min_quality = min_quality

    def run(self, context: AgentContext) -> TeamRunResult:
        if context.portfolio is None:
            portfolio = PortfolioState(equity=0.0, balance=0.0)
        else:
            portfolio = context.portfolio

        signals = tuple(agent.analyze(context).normalized() for agent in self.specialists)
        proposal = self.portfolio_manager.propose(context.market.symbol, list(signals), self.min_quality)
        verdict: RiskVerdict = self.risk_manager.evaluate(
            proposal,
            portfolio,
            spread_points=context.market.spread_points,
        )
        decision = TeamDecision(
            ts=utcnow(),
            symbol=context.market.symbol,
            proposal=proposal,
            risk_verdict=verdict,
            signals=signals,
        )
        execution = self.execution_agent.prepare(decision)
        return TeamRunResult(signals=signals, decision=decision, execution=execution)
