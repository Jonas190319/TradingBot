from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"
    NO_TRADE = "no_trade"


class Regime(str, Enum):
    NEWS = "news"
    TREND = "trend"
    RANGE = "range"
    BREAKOUT = "breakout"
    CHAOS = "chaos"
    UNKNOWN = "unknown"


class Decision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    WAIT = "wait"
    NO_TRADE = "no_trade"


@dataclass(frozen=True)
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    ts: datetime
    bid: float
    ask: float
    bars: tuple[Bar, ...] = ()
    atr: float | None = None
    spread_points: float | None = None
    session: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0


@dataclass(frozen=True)
class EconomicEvent:
    ts: datetime
    currency: str
    title: str
    importance: int  # 1 low, 2 medium, 3 high
    actual: float | None = None
    consensus: float | None = None
    previous: float | None = None
    unit: str | None = None


@dataclass(frozen=True)
class NewsItem:
    ts: datetime
    headline: str
    symbols: tuple[str, ...] = ()
    currencies: tuple[str, ...] = ()
    sentiment: float = 0.0  # -1..1
    severity: float = 0.0  # 0..1
    source: str | None = None


@dataclass(frozen=True)
class PortfolioState:
    equity: float
    balance: float
    daily_pnl_pct: float = 0.0
    weekly_pnl_pct: float = 0.0
    drawdown_pct: float = 0.0
    open_risk_pct: float = 0.0
    open_positions: int = 0
    symbol_exposure: dict[str, float] = field(default_factory=dict)
    currency_exposure: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentSignal:
    ts: datetime
    symbol: str
    agent_type: str
    direction: Direction
    confidence: float
    risk_score: float
    recommendation: str
    rationale: str
    payload: dict[str, Any] = field(default_factory=dict)

    def normalized(self) -> "AgentSignal":
        return AgentSignal(
            ts=self.ts,
            symbol=self.symbol,
            agent_type=self.agent_type,
            direction=self.direction,
            confidence=max(0.0, min(100.0, float(self.confidence))),
            risk_score=max(0.0, min(100.0, float(self.risk_score))),
            recommendation=self.recommendation,
            rationale=self.rationale,
            payload=self.payload,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self.normalized())
        data["ts"] = self.ts.astimezone(timezone.utc).isoformat()
        data["direction"] = self.direction.value
        return data


@dataclass(frozen=True)
class TradeProposal:
    ts: datetime
    symbol: str
    direction: Direction
    quality_score: float
    confidence: float
    regime: Regime
    strategy: str
    stop_distance_points: float | None
    target_distance_points: float | None
    suggested_risk_pct: float
    rationale: str
    components: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class RiskVerdict:
    decision: Decision
    approved_risk_pct: float
    reasons: tuple[str, ...]
    hard_veto: bool = False


@dataclass(frozen=True)
class TeamDecision:
    ts: datetime
    symbol: str
    proposal: TradeProposal | None
    risk_verdict: RiskVerdict
    signals: tuple[AgentSignal, ...]

    @property
    def executable(self) -> bool:
        return (
            self.proposal is not None
            and self.proposal.direction in (Direction.LONG, Direction.SHORT)
            and self.risk_verdict.decision == Decision.APPROVE
            and not self.risk_verdict.hard_veto
        )


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def last(values: Iterable[float], n: int) -> list[float]:
    vals = list(values)
    return vals[-n:] if n > 0 else vals
