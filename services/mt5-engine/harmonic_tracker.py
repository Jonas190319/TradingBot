"""Causal, read-only harmonic pattern lifecycle for research.

Call update once per CLOSED bar, in timestamp order. Detection uses only
confirmed pivots. Each pattern ID is stable across repeated detections.
No orders, uploads, or changes to live scanner.
"""
from dataclasses import dataclass
from hashlib import sha256

from services.decision_engine.harmonic_patterns import classify_completion_zone


def pattern_id(symbol, match, pivots):
    """Unique identity from instrument, pattern, direction and five swing timestamps."""
    parts = [symbol, match.pattern, match.direction]
    parts.extend(f"{p.timestamp}:{p.kind}:{p.price:.12g}" for p in pivots)
    return sha256("|".join(parts).encode("utf-8")).hexdigest()[:20]


@dataclass
class TrackedPattern:
    id: str
    pattern: str
    direction: str
    d_price: float
    discovered_at: int
    last_seen_at: int
    status: str = "active"
    signaled: bool = False


class HarmonicTracker:
    """Track detected patterns independently of subsequent swing selection.

    A pattern expires after max_age_bars, invalidates at the directional ATR
    threshold, or signals once upon an in-zone directional confirmation.
    No stale session is bridged: reset() when a bar gap is detected.
    """

    def __init__(self, max_age_bars=48, inner_atr=0.75, invalidation_atr=1.5):
        if not 1 <= max_age_bars <= 288:
            raise ValueError("Invalid maximum pattern age")
        self.max_age_bars = max_age_bars
        self.inner_atr = inner_atr
        self.invalidation_atr = invalidation_atr
        self.active = {}
        self.seen_ids = set()

    def reset(self):
        self.active.clear()

    def update(self, bar_index, candle, atr, detections=()):
        """Return events, with at most one signal per unique pattern ID.

        detections: iterable of (symbol, harmonic_match, five_confirmed_pivots).
        A previously seen pattern cannot be rediscovered as a new trade.
        """
        events = []
        for symbol, match, pivots in detections:
            if len(pivots) != 5:
                raise ValueError("Need five confirmed pivots")
            key = pattern_id(symbol, match, pivots)
            if key not in self.seen_ids:
                self.seen_ids.add(key)
                self.active[key] = TrackedPattern(
                    key, match.pattern, match.direction, pivots[-1].price,
                    bar_index, bar_index,
                )
                events.append(("discovered", key, match.pattern))
            elif key in self.active:
                self.active[key].last_seen_at = bar_index

        for key, state in list(self.active.items()):
            if bar_index - state.discovered_at >= self.max_age_bars:
                state.status = "expired"
                events.append(("expired", key, state.pattern))
                del self.active[key]
                continue
            zone = classify_completion_zone(
                state.direction, state.d_price, candle.close, atr,
                inner_atr=self.inner_atr, invalidation_atr=self.invalidation_atr,
            )
            if zone["status"] == "invalidated":
                state.status = "invalidated"
                events.append(("invalidated", key, state.pattern))
                del self.active[key]
            elif zone["status"] == "entry_zone":
                bullish = state.direction == "long"
                confirmed = candle.close > candle.open if bullish else candle.close < candle.open
                if confirmed and not state.signaled:
                    state.signaled = True
                    state.status = "signaled"
                    events.append(("signal", key, state.pattern))
                    del self.active[key]
                else:
                    events.append(("zone_unconfirmed", key, state.pattern))
        return events
