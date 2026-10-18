"""Conservative OHLC-only research outcomes; no broker orders or data access.

A position is assumed filled at the supplied entry BEFORE the first future bar.
If a bar touches stop and target, result is ambiguous (never count as a win).
No slippage, spread, fees, gaps or intrabar sequencing is modeled.
"""
from math import isfinite


def evaluate_outcome(side, entry, stop, target, future_bars, max_bars=48):
    if side not in ("long", "short"):
        raise ValueError("side must be long or short")
    entry, stop, target = map(float, (entry, stop, target))
    if not all(map(isfinite, (entry, stop, target))):
        raise ValueError("Non-finite price")
    if not ((side == "long" and stop < entry < target) or
            (side == "short" and target < entry < stop)):
        raise ValueError("Invalid risk geometry")
    if not isinstance(max_bars, int) or max_bars < 1:
        raise ValueError("max_bars must be positive")
    risk = abs(entry - stop)
    reward_r = abs(target - entry) / risk
    for idx, bar in enumerate(future_bars):
        if idx >= max_bars:
            break
        high, low = float(bar["high"]), float(bar["low"])
        if not all(map(isfinite, (high, low))) or high < low:
            raise ValueError("Invalid OHLC bar")
        hit_stop = low <= stop if side == "long" else high >= stop
        hit_target = high >= target if side == "long" else low <= target
        if hit_stop and hit_target:
            return {"outcome": "ambiguous", "bars_held": idx + 1, "r": None}
        if hit_stop:
            return {"outcome": "stop", "bars_held": idx + 1, "r": -1.0}
        if hit_target:
            return {"outcome": "target", "bars_held": idx + 1, "r": reward_r}
    return {"outcome": "unresolved", "bars_held": min(max_bars, len(future_bars)), "r": None}


def summarize_outcomes(outcomes):
    """Exclude ambiguous/unresolved from win rate and mean R; report their counts."""
    results = list(outcomes)
    closed = [x for x in results if x["outcome"] in ("stop", "target")]
    wins = sum(x["outcome"] == "target" for x in closed)
    return {
        "signals": len(results),
        "resolved": len(closed),
        "wins": wins,
        "losses": len(closed) - wins,
        "ambiguous": sum(x["outcome"] == "ambiguous" for x in results),
        "unresolved": sum(x["outcome"] == "unresolved" for x in results),
        "win_rate": wins / len(closed) if closed else None,
        "mean_r": sum(x["r"] for x in closed) / len(closed) if closed else None,
    }
