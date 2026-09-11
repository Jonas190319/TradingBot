from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, Iterable, List

from models import MarketSnapshot


@dataclass
class PreTradeEvent:
    ts: datetime
    symbol: str
    strategy: str
    candidate_id: str
    stage: str
    score: float
    snapshot: MarketSnapshot
    notes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ts": self.ts.astimezone(timezone.utc).isoformat(),
            "symbol": self.symbol,
            "strategy": self.strategy,
            "candidate_id": self.candidate_id,
            "stage": self.stage,
            "score": self.score,
            "snapshot": self.snapshot.to_dict(),
            "notes": self.notes,
        }


class PreTradeRecorder:
    """Records how a setup develops before an order exists.

    The recorder is intentionally strategy-agnostic. It keeps a rolling market
    context buffer and a separate immutable event history for every candidate.
    """

    def __init__(self, context_minutes: int = 60, max_points_per_symbol: int = 720):
        self.context_minutes = context_minutes
        self.market_buffer: Dict[str, Deque[MarketSnapshot]] = defaultdict(
            lambda: deque(maxlen=max_points_per_symbol)
        )
        self.events: Dict[str, List[PreTradeEvent]] = defaultdict(list)

    def observe(self, snapshot: MarketSnapshot) -> None:
        self.market_buffer[snapshot.symbol].append(snapshot)
        self._trim(snapshot.symbol, snapshot.ts)

    def record_candidate(
        self,
        *,
        candidate_id: str,
        strategy: str,
        stage: str,
        score: float,
        snapshot: MarketSnapshot,
        notes: Dict[str, Any] | None = None,
    ) -> None:
        self.observe(snapshot)
        self.events[candidate_id].append(
            PreTradeEvent(
                ts=snapshot.ts,
                symbol=snapshot.symbol,
                strategy=strategy,
                candidate_id=candidate_id,
                stage=stage,
                score=score,
                snapshot=snapshot,
                notes=notes or {},
            )
        )

    def history(self, candidate_id: str) -> List[PreTradeEvent]:
        return list(self.events.get(candidate_id, []))

    def context(self, symbol: str) -> List[MarketSnapshot]:
        return list(self.market_buffer.get(symbol, []))

    def score_slope(self, candidate_id: str, lookback: int = 5) -> float:
        events = self.events.get(candidate_id, [])
        points = events[-lookback:]
        if len(points) < 2:
            return 0.0
        return (points[-1].score - points[0].score) / max(1, len(points) - 1)

    def summarize(self, candidate_id: str) -> Dict[str, Any]:
        events = self.history(candidate_id)
        if not events:
            return {"candidate_id": candidate_id, "events": 0}
        return {
            "candidate_id": candidate_id,
            "events": len(events),
            "first_score": events[0].score,
            "last_score": events[-1].score,
            "score_slope": self.score_slope(candidate_id),
            "first_ts": events[0].ts.astimezone(timezone.utc).isoformat(),
            "last_ts": events[-1].ts.astimezone(timezone.utc).isoformat(),
            "stages": [e.stage for e in events],
        }

    def export_events(self, candidate_id: str) -> List[Dict[str, Any]]:
        return [event.to_dict() for event in self.history(candidate_id)]

    def _trim(self, symbol: str, now: datetime) -> None:
        cutoff = now - timedelta(minutes=self.context_minutes)
        buf = self.market_buffer[symbol]
        while buf and buf[0].ts < cutoff:
            buf.popleft()
