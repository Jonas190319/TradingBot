"""Closed-bar, no-lookahead supply/demand research zones.

A zone is formed from a base candle followed by an impulsive departure.
It becomes available only AFTER the departure bar closes. The latest
closed candle may retest it. No claim of actual institutional orders.
"""
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class Zone:
    side: str
    lower: float
    upper: float
    origin_ts: str
    confirmed_ts: str
    touches: int
    fresh: bool
    departure_atr: float


def detect_zones(bars: Sequence, atr: float, *, lookback: int = 100,
                 impulse_atr: float = 1.5, max_base_atr: float = 1.2) -> list[Zone]:
    if atr <= 0 or len(bars) < 5:
        return []
    recent = bars[-lookback:]
    zones = []
    # Base index i, departure at i+1; require i+1 to be closed.
    for i in range(1, len(recent) - 1):
        base, departure = recent[i], recent[i + 1]
        if base.high <= base.low or (base.high - base.low) > max_base_atr * atr:
            continue
        delta = departure.close - base.close
        if abs(delta) < impulse_atr * atr:
            continue
        side = "demand" if delta > 0 else "supply"
        if side == "demand" and departure.close <= base.high:
            continue
        if side == "supply" and departure.close >= base.low:
            continue
        lower, upper = base.low, base.high
        # Count retests strictly after departure; exclude the confirming bar.
        subsequent = recent[i + 2:]
        invalid = any(b.close < lower if side == "demand" else b.close > upper for b in subsequent)
        if invalid:
            continue
        touches = sum(b.low <= upper and b.high >= lower for b in subsequent)
        zones.append(Zone(side, lower, upper, base.ts.isoformat(),
                          departure.ts.isoformat(), touches, touches == 0,
                          abs(delta) / atr))
    return zones


def zone_features(bars: Sequence, atr: float) -> dict:
    zones = detect_zones(bars, atr)
    price = bars[-1].close
    # A zone is relevant when the latest closed candle overlaps it.
    relevant = [z for z in zones if bars[-1].low <= z.upper and bars[-1].high >= z.lower]
    # Prefer the most recently confirmed zone; never claim probability.
    z = relevant[-1] if relevant else None
    return {
        "sd_zone_present": z is not None,
        "sd_zone_side": z.side if z else "none",
        "sd_zone_lower": z.lower if z else None,
        "sd_zone_upper": z.upper if z else None,
        "sd_zone_origin_ts": z.origin_ts if z else None,
        "sd_zone_confirmed_ts": z.confirmed_ts if z else None,
        "sd_zone_touches": z.touches if z else None,
        "sd_zone_fresh": z.fresh if z else False,
        "sd_zone_departure_atr": z.departure_atr if z else None,
        "sd_zone_reaction": (
            (price > z.upper and bars[-1].close > bars[-1].open) if z and z.side == "demand"
            else (price < z.lower and bars[-1].close < bars[-1].open) if z else False
        ),
        "sd_method": "closed-m5-impulse-base-v1-heuristic",
        "sd_zone_count": len(zones),
    }
