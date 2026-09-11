from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"
    NO_TRADE = "no_trade"


class Regime(str, Enum):
    TREND = "trend"
    RANGE = "range"
    BREAKOUT = "breakout"
    HIGH_VOL = "high_vol"
    LOW_VOL = "low_vol"
    NEWS = "news"
    DISLOCATION = "dislocation"
    UNKNOWN = "unknown"


class Decision(str, Enum):
    APPROVE = "approve"
    APPROVE_REDUCED = "approve_reduced"
    SHADOW = "shadow"
    REJECT = "reject"


class ManagementAction(str, Enum):
    HOLD = "hold"
    REDUCE = "reduce"
    MOVE_SL = "move_sl"
    PARTIAL = "partial"
    CLOSE = "close"


@dataclass(frozen=True)
class MarketSnapshot:
    ts: datetime
    symbol: str
    bid: float
    ask: float
    spread: float
    features: Dict[str, float | int | str | bool | None] = field(default_factory=dict)

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["ts"] = self.ts.astimezone(timezone.utc).isoformat()
        return payload


@dataclass(frozen=True)
class AnalystView:
    agent: str
    symbol: str
    direction: Direction
    confidence: float
    rationale: str
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TradeCandidate:
    candidate_id: str
    created_at: datetime
    symbol: str
    strategy: str
    direction: Direction
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: Optional[float]
    setup_score: float
    regime: Regime
    invalidation: str
    management_plan: Dict[str, Any]
    evidence: Dict[str, Any] = field(default_factory=dict)
    valid_until: Optional[datetime] = None

    @property
    def stop_distance(self) -> float:
        return abs(self.entry - self.stop_loss)

    @property
    def reward_distance(self) -> float:
        return abs(self.take_profit_1 - self.entry)

    @property
    def rr(self) -> float:
        return self.reward_distance / self.stop_distance if self.stop_distance > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.astimezone(timezone.utc).isoformat()
        payload["valid_until"] = self.valid_until.astimezone(timezone.utc).isoformat() if self.valid_until else None
        payload["direction"] = self.direction.value
        payload["regime"] = self.regime.value
        payload["rr"] = self.rr
        return payload


@dataclass
class CommitteeDecision:
    candidate_id: str
    decision: Decision
    score: float
    rationale: str
    approved_risk_pct: float
    weights: Dict[str, float]
    analyst_votes: List[AnalystView] = field(default_factory=list)


@dataclass
class TradeState:
    trade_id: str
    candidate: TradeCandidate
    opened_at: datetime
    entry_price: float
    current_price: float
    initial_stop: float
    current_stop: float
    tp1: float
    tp2: Optional[float]
    risk_amount: float
    position_size: float
    mfe_r: float = 0.0
    mae_r: float = 0.0
    realized_r: float = 0.0
    closed_at: Optional[datetime] = None
    exit_price: Optional[float] = None
    actions: List[Dict[str, Any]] = field(default_factory=list)

    def r_multiple(self, price: Optional[float] = None) -> float:
        p = self.current_price if price is None else price
        risk_distance = abs(self.entry_price - self.initial_stop)
        if risk_distance <= 0:
            return 0.0
        raw = (p - self.entry_price) / risk_distance
        return raw if self.candidate.direction == Direction.LONG else -raw
