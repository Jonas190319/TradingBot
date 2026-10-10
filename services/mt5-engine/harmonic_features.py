"""Confirmed-pivot harmonic research features from closed OHLC bars only.

A pivot at i is confirmed only after 'right' later CLOSED candles.
Latest D pivot may be older than the latest candle; require a fresh reaction
near D and reject stale detections. No broker orders or probability claims.
"""
from __future__ import annotations

from services.decision_engine.harmonic_patterns import Pivot, detect_xabcd, detect_shark


def confirmed_pivots(bars, left=3, right=3):
    out = []
    for i in range(left, len(bars) - right):
        center = bars[i]
        before = bars[i-left:i]
        after = bars[i+1:i+right+1]
        high = all(center.high > b.high for b in (*before, *after))
        low = all(center.low < b.low for b in (*before, *after))
        if high == low:
            continue
        kind = 'high' if high else 'low'
        price = center.high if high else center.low
        p = Pivot(center.ts.isoformat(), price, kind)
        if out and out[-1][1].kind == kind:
            prior = out[-1][1]
            if (kind == 'high' and price > prior.price) or (kind == 'low' and price < prior.price):
                out[-1] = (i, p)
        else:
            out.append((i, p))
    return out


def harmonic_features(bars, atr):
    empty = {'harmonic_matches': [], 'harmonic_method': 'confirmed-3x3-pivots-v1',
             'harmonic_ready': False}
    if atr <= 0 or len(bars) < 30:
        return empty
    pivots = confirmed_pivots(bars)
    if len(pivots) < 5:
        return empty
    last_five = pivots[-5:]
    d_index, d = last_five[-1]
    # Freshness and reaction are mandatory; no retroactive entry at pivot D.
    if len(bars) - 1 - d_index > 8:
        return empty
    close, candle = bars[-1].close, bars[-1]
    if abs(close - d.price) > 1.5 * atr:
        return empty
    matches = detect_xabcd([p for _, p in last_five]) + detect_shark([p for _, p in last_five])
    output = []
    for match in matches:
        bullish = match.direction == 'long'
        if (bullish and candle.close <= candle.open) or (not bullish and candle.close >= candle.open):
            continue
        output.append({'pattern': match.pattern, 'direction': match.direction,
                       'pivot_price': d.price, 'pivot_ts': d.timestamp,
                       'confirmed_at': bars[d_index+3].ts.isoformat(),
                       'ratios': {k: getattr(match, k) for k in
                                  ('ab_xa', 'bc_ab', 'cd_bc', 'ad_xa') if hasattr(match, k)},
                       'tolerance': match.tolerance,
                       'provenance': 'confirmed closed M5 bars; heuristic ratios'})
    return {**empty, 'harmonic_ready': True, 'harmonic_matches': output}
