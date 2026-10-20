"""Closed-candle candlestick pattern research features.

All patterns are descriptive, not entry instructions or proven predictors.
OHLC inputs must be chronological and consist only of completed bars.
"""
from dataclasses import dataclass
from math import isfinite

@dataclass(frozen=True)
class CandlePattern:
    name: str
    direction: str
    candle_index: int
    strength: float

def detect_candle_patterns(bars, *, doji_body_ratio=0.10,
                           long_wick_body_multiple=2.0):
    if not 0<doji_body_ratio<1 or long_wick_body_multiple<=0:
        raise ValueError("Invalid thresholds")
    out=[]
    for i,b in enumerate(bars):
        o,h,l,c=(float(b[k]) for k in ("open","high","low","close"))
        if not all(isfinite(x) for x in (o,h,l,c)) or h<max(o,c) or l>min(o,c) or h<=l:
            raise ValueError("Invalid OHLC bar")
        span=h-l; body=abs(c-o)
        upper=h-max(o,c); lower=min(o,c)-l
        if body/span<=doji_body_ratio:
            out.append(CandlePattern("doji","neutral",i,1-body/span))
        if lower>=long_wick_body_multiple*max(body,span*0.02) and upper<=max(body,span*0.1):
            out.append(CandlePattern("hammer_shape","bullish",i,min(1,lower/span)))
        if upper>=long_wick_body_multiple*max(body,span*0.02) and lower<=max(body,span*0.1):
            out.append(CandlePattern("shooting_star_shape","bearish",i,min(1,upper/span)))
        if body/span>=0.7:
            out.append(CandlePattern("bullish_marubozu_like" if c>o else "bearish_marubozu_like",
                                     "bullish" if c>o else "bearish",i,body/span))
        if i==0:
            continue
        p=bars[i-1]; po=float(p["open"]); pc=float(p["close"])
        if pc<po and c>o and o<=pc and c>=po:
            out.append(CandlePattern("bullish_engulfing","bullish",i,body/span))
        if pc>po and c<o and o>=pc and c<=po:
            out.append(CandlePattern("bearish_engulfing","bearish",i,body/span))
        if h<=float(p["high"]) and l>=float(p["low"]):
            out.append(CandlePattern("inside_bar","neutral",i,1-span/max(float(p["high"])-float(p["low"]),span)))
        if h>float(p["high"]) and l<float(p["low"]):
            out.append(CandlePattern("outside_bar","bullish" if c>o else "bearish",i,body/span))
    return out

def latest_pattern_features(bars, lookback=3):
    """Feature snapshot: most recent patterns with relative age in closed bars."""
    if lookback<1:
        raise ValueError("lookback must be positive")
    matches=detect_candle_patterns(bars)
    end=len(bars)-1
    return tuple({"pattern":p.name,"direction":p.direction,
                  "age_bars":end-p.candle_index,"strength":round(p.strength,4)}
                 for p in matches if end-p.candle_index<lookback)
