"""Causal harmonic XABCD research detector. No order execution.

Input: five *confirmed* alternating swing pivots (timestamp, price, kind).
The caller must confirm pivots using only data available at evaluation time.
Ratios are hypotheses, not profitability claims.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Optional, Sequence


@dataclass(frozen=True)
class Pivot:
    timestamp: str
    price: float
    kind: str  # "high" or "low"


@dataclass(frozen=True)
class HarmonicMatch:
    pattern: str
    direction: str
    ab_xa: float
    bc_ab: float
    cd_bc: float
    ad_xa: float
    tolerance: float


# Approximate published Fibonacci zones. Validate empirically per market.
RULES = {
    "gartley": {"ab_xa": (0.618, 0.618), "bc_ab": (0.382, 0.886), "cd_bc": (1.272, 1.618), "ad_xa": (0.786, 0.786)},
    "bat": {"ab_xa": (0.382, 0.500), "bc_ab": (0.382, 0.886), "cd_bc": (1.618, 2.618), "ad_xa": (0.886, 0.886)},
    "butterfly": {"ab_xa": (0.786, 0.786), "bc_ab": (0.382, 0.886), "cd_bc": (1.618, 2.618), "ad_xa": (1.270, 1.618)},
    "crab": {"ab_xa": (0.382, 0.618), "bc_ab": (0.382, 0.886), "cd_bc": (2.240, 3.618), "ad_xa": (1.618, 1.618)},
}
# Shark uses a different 0-X-A-B-C structure and must NOT be mislabeled XABCD.


def _in_zone(value: float, zone: tuple[float, float], tolerance: float) -> bool:
    return zone[0] * (1 - tolerance) <= value <= zone[1] * (1 + tolerance)


def detect_xabcd(pivots: Sequence[Pivot], tolerance: float = 0.05) -> list[HarmonicMatch]:
    """Return research matches; never an executable trading signal."""
    if len(pivots) != 5 or not (0 <= tolerance <= 0.15):
        return []
    if any(not isfinite(p.price) or p.price <= 0 or p.kind not in {"high", "low"} for p in pivots):
        return []
    if any(pivots[i].timestamp >= pivots[i + 1].timestamp for i in range(4)):
        return []
    if any(pivots[i].kind == pivots[i + 1].kind for i in range(4)):
        return []
    x, a, b, c, d = (p.price for p in pivots)
    legs = (a - x, b - a, c - b, d - c)
    if any(abs(v) <= 1e-12 for v in legs):
        return []
    if any(legs[i] * legs[i + 1] >= 0 for i in range(3)):
        return []
    # XA and AD must have opposing signs for retracement and extension patterns.
    if (d - a) * (a - x) >= 0:
        return []
    ratios = {
        "ab_xa": abs(b - a) / abs(a - x),
        "bc_ab": abs(c - b) / abs(b - a),
        "cd_bc": abs(d - c) / abs(c - b),
        "ad_xa": abs(d - a) / abs(a - x),
    }
    direction = "long" if pivots[-1].kind == "low" else "short"
    return [
        HarmonicMatch(name, direction, **ratios, tolerance=tolerance)
        for name, rule in RULES.items()
        if all(_in_zone(ratios[key], zone, tolerance) for key, zone in rule.items())
    ]


@dataclass(frozen=True)
class SharkMatch:
    """Separate 0-X-A-B-C structure, not an XABCD match."""
    pattern: str
    direction: str
    ox_xa: float
    ab_xa: float
    bc_ab: float
    oc_ox: float
    tolerance: float


def detect_shark(pivots: Sequence[Pivot], tolerance: float = 0.05) -> list[SharkMatch]:
    """Conservative 0XABC research heuristic; validate ratios before production.

    X-A retraces 0-X by 1.13-1.618, A-B extends X-A by 1.13-1.618,
    B-C extends A-B by 1.618-2.24, and C returns near 0.886-1.13 of O-X.
    These are configurable hypotheses rather than a canonical universal rule.
    """
    if len(pivots) != 5 or not 0 <= tolerance <= 0.15:
        return []
    if any(not isfinite(p.price) or p.price <= 0 or p.kind not in {'low', 'high'} for p in pivots):
        return []
    if any(pivots[i].timestamp >= pivots[i+1].timestamp or pivots[i].kind == pivots[i+1].kind
           for i in range(4)):
        return []
    o, x, a, b, c = (p.price for p in pivots)
    legs = [x-o, a-x, b-a, c-b]
    if min(map(abs, legs)) <= 1e-12 or any(legs[i]*legs[i+1] >= 0 for i in range(3)):
        return []
    ratios = (abs(a-x)/abs(x-o), abs(b-a)/abs(a-x),
              abs(c-b)/abs(b-a), abs(c-o)/abs(x-o))
    zones = ((1.13, 1.618), (1.13, 1.618), (1.618, 2.24), (0.886, 1.13))
    if not all(_in_zone(v, z, tolerance) for v, z in zip(ratios, zones)):
        return []
    return [SharkMatch('shark', 'long' if pivots[-1].kind == 'low' else 'short',
                       *ratios, tolerance)]
