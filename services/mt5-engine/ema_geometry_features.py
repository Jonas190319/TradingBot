"""Causal, ATR-normalized EMA geometry features for completed candles.

Pure computation, no MT5 connection or order calls.
"""
from dataclasses import dataclass
from math import isfinite

@dataclass(frozen=True)
class EMAGeometry:
    price_ema20_atr: float
    price_ema50_atr: float
    price_ema200_atr: float
    ema20_ema50_atr: float
    ema50_ema200_atr: float
    ema20_ema200_atr: float
    ema20_slope_atr: float
    ema50_slope_atr: float
    ema200_slope_atr: float
    spread20_50_change_atr: float
    spread50_200_change_atr: float
    alignment: str

def ema_geometry(close, ema20, ema50, ema200, atr14,
                 prior_ema20, prior_ema50, prior_ema200):
    values = (close, ema20, ema50, ema200, atr14,
              prior_ema20, prior_ema50, prior_ema200)
    if not all(isfinite(float(x)) for x in values) or atr14 <= 0:
        raise ValueError("Finite values and positive ATR required")
    norm = lambda x: x / atr14
    alignment = ("bullish" if ema20 > ema50 > ema200 else
                 "bearish" if ema20 < ema50 < ema200 else "mixed")
    return EMAGeometry(
        norm(close-ema20), norm(close-ema50), norm(close-ema200),
        norm(ema20-ema50), norm(ema50-ema200), norm(ema20-ema200),
        norm(ema20-prior_ema20), norm(ema50-prior_ema50),
        norm(ema200-prior_ema200),
        norm((ema20-ema50)-(prior_ema20-prior_ema50)),
        norm((ema50-ema200)-(prior_ema50-prior_ema200)),
        alignment,
    )

# Caller must supply EMA and ATR values computed only from completed
# historical candles. Prior EMA values must precede the observation.
# Thresholds are research hypotheses, never assumed profitable.
