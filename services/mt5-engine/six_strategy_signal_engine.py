"""Deterministic closed-bar candidate signals for the six-strategy research portfolio.

Research only: no broker connectivity, orders, scheduling or profitability claims.
Inputs are chronological *completed* OHLCV bars; no forming bar is accepted.
Session opening ranges and prior-day profiles are provided by the caller.
"""
from dataclasses import dataclass
from math import isfinite
from statistics import mean, pstdev
from typing import Optional

@dataclass(frozen=True)
class Candidate:
    strategy: str
    side: str
    entry: float
    stop: float
    target: float
    reason: str

def ema(values, period):
    if len(values) < period:
        return None
    alpha = 2 / (period + 1)
    out = mean(values[:period])
    for v in values[period:]:
        out = alpha * v + (1-alpha) * out
    return out

def rsi(values, period=14):
    if len(values) < period+1:
        return None
    changes = [values[i]-values[i-1] for i in range(1,len(values))]
    gains = [max(d,0) for d in changes]
    losses = [max(-d,0) for d in changes]
    avg_gain = mean(gains[:period])
    avg_loss = mean(losses[:period])
    for g,l in zip(gains[period:],losses[period:]):
        avg_gain = (avg_gain*(period-1)+g)/period
        avg_loss = (avg_loss*(period-1)+l)/period
    if avg_loss == 0:
        return 100.0 if avg_gain else 50.0
    return 100 - 100/(1+avg_gain/avg_loss)

def atr(bars, period=14):
    if len(bars) < period+1:
        return None
    trs = [max(bars[i]["high"]-bars[i]["low"],
               abs(bars[i]["high"]-bars[i-1]["close"]),
               abs(bars[i]["low"]-bars[i-1]["close"]))
           for i in range(1,len(bars))]
    value = mean(trs[:period])
    for tr in trs[period:]:
        value = (value*(period-1)+tr)/period
    return value

def adx(bars, period=14):
    if len(bars) < 2*period+1:
        return None
    trs, plus, minus = [], [], []
    for i in range(1,len(bars)):
        a,b = bars[i],bars[i-1]
        up = a["high"]-b["high"]
        down = b["low"]-a["low"]
        plus.append(up if up > down and up > 0 else 0.0)
        minus.append(down if down > up and down > 0 else 0.0)
        trs.append(max(a["high"]-a["low"],abs(a["high"]-b["close"]),abs(a["low"]-b["close"])))
    def smooth(v):
        x = sum(v[:period])
        result = [x]
        for y in v[period:]:
            x = x - x/period + y
            result.append(x)
        return result
    t,p,m = smooth(trs),smooth(plus),smooth(minus)
    dx = []
    for tv,pv,mv in zip(t,p,m):
        pi,mi = (100*pv/tv,100*mv/tv) if tv else (0,0)
        dx.append(100*abs(pi-mi)/(pi+mi) if pi+mi else 0)
    if len(dx)<period:
        return None
    value = mean(dx[:period])
    for v in dx[period:]:
        value = (value*(period-1)+v)/period
    return value

def _candidate(name, side, entry, stop, rr, reason):
    risk = entry-stop if side=="long" else stop-entry
    if not isfinite(risk) or risk<=0:
        return None
    return Candidate(name,side,entry,stop,entry+rr*risk*(1 if side=="long" else -1),reason)

def scan(bars, *, prior_profile=None, opening_range=None, tick_size=None, rr=2.0):
    """Return rule-based *candidates*, not authorized trades.

    prior_profile: object with vah/val/poc from an already completed session.
    opening_range: (high,low) calculated from a completed 15-minute session.
    """
    if len(bars)<205 or rr<=0:
        return []
    if any(not all(isfinite(float(b[k])) for k in ("open","high","low","close"))
           or b["high"]<max(b["open"],b["close"])
           or b["low"]>min(b["open"],b["close"]) for b in bars):
        raise ValueError("Invalid completed OHLC bars")
    c = [float(b["close"]) for b in bars]
    last,prev = bars[-1],bars[-2]
    vol = atr(bars)
    if not vol or vol<=0:
        return []
    e20,e50,e200 = (ema(c,n) for n in (20,50,200))
    r,pr = rsi(c),rsi(c[:-1])
    strength = adx(bars)
    result = []
    def add(candidate):
        if candidate:
            result.append(candidate)
    # EMA pullback: prior candle touches EMA20, confirmation closes above/below;
    # RSI crosses 50 with trend alignment, no chase beyond 0.75 ATR.
    if e20>e50>e200 and prev["low"]<=e20 and last["close"]>e20 and last["close"]>prev["close"] and pr<=50<r and (last["close"]-e20)/vol<=0.75:
        add(_candidate("ema_pullback_rsi","long",last["close"],min(prev["low"],last["low"])-0.2*vol,rr,"bullish_ema_alignment_rsi_cross"))
    if e20<e50<e200 and prev["high"]>=e20 and last["close"]<e20 and last["close"]<prev["close"] and pr>=50>r and (e20-last["close"])/vol<=0.75:
        add(_candidate("ema_pullback_rsi","short",last["close"],max(prev["high"],last["high"])+0.2*vol,rr,"bearish_ema_alignment_rsi_cross"))
    # Volume-profile reversals require a non-trending market.
    if prior_profile is not None and strength is not None and strength<20:
        if prev["low"]<prior_profile.val and prior_profile.val<last["close"]<prior_profile.poc and r>pr:
            add(_candidate("volume_profile_value_area_reversal","long",last["close"],min(prev["low"],last["low"])-0.2*vol,rr,"reclaim_val"))
        if prev["high"]>prior_profile.vah and prior_profile.poc<last["close"]<prior_profile.vah and r<pr:
            add(_candidate("volume_profile_value_area_reversal","short",last["close"],max(prev["high"],last["high"])+0.2*vol,rr,"reject_vah"))
    # Opening range: breakout already completed on previous candle, retest now.
    if opening_range is not None:
        hi,lo = opening_range
        if hi<=lo:
            raise ValueError("Invalid opening range")
        if prev["close"]>hi and last["low"]<=hi and last["close"]>hi and last["close"]>last["open"]:
            add(_candidate("opening_range_breakout_retest","long",last["close"],min(last["low"],hi-0.2*vol),rr,"opening_range_upper_retest"))
        if prev["close"]<lo and last["high"]>=lo and last["close"]<lo and last["close"]<last["open"]:
            add(_candidate("opening_range_breakout_retest","short",last["close"],max(last["high"],lo+0.2*vol),rr,"opening_range_lower_retest"))
    # Bollinger re-entry with RSI crossing out of extreme in low-ADX regime.
    basis=mean(c[-20:]); sd=pstdev(c[-20:])
    if strength is not None and strength<20 and sd>0:
        if prev["close"]<basis-2*sd and last["close"]>basis-2*sd and pr<30<=r:
            add(_candidate("bollinger_rsi_mean_reversion","long",last["close"],min(last["low"],prev["low"])-0.2*vol,1.0,"lower_band_reentry"))
        if prev["close"]>basis+2*sd and last["close"]<basis+2*sd and pr>70>=r:
            add(_candidate("bollinger_rsi_mean_reversion","short",last["close"],max(last["high"],prev["high"])+0.2*vol,1.0,"upper_band_reentry"))
    # Profile breakout: prior bar broke value area, current bar retests and holds.
    if prior_profile is not None and strength is not None and strength>=25:
        if prev["close"]>prior_profile.vah and last["low"]<=prior_profile.vah and last["close"]>prior_profile.vah:
            add(_candidate("volume_profile_breakout_adx","long",last["close"],min(last["low"],prior_profile.vah-0.2*vol),rr,"vah_breakout_retest"))
        if prev["close"]<prior_profile.val and last["high"]>=prior_profile.val and last["close"]<prior_profile.val:
            add(_candidate("volume_profile_breakout_adx","short",last["close"],max(last["high"],prior_profile.val+0.2*vol),rr,"val_breakout_retest"))
    # Supply/demand: 3-bar base, 1.5 ATR impulse confirmed on previous
    # completed bar, first retest on current bar. Excludes older zone history.
    base=bars[-5:-2]; impulse=prev
    base_hi=max(x["high"] for x in base); base_lo=min(x["low"] for x in base)
    if base_hi-base_lo<=1.2*vol:
        if impulse["close"]>base_hi+1.5*vol and last["low"]<=base_hi and last["close"]>base_hi and last["close"]>last["open"]:
            add(_candidate("supply_demand_retest","long",last["close"],base_lo-0.2*vol,rr,"fresh_demand_impulse_retest"))
        if impulse["close"]<base_lo-1.5*vol and last["high"]>=base_lo and last["close"]<base_lo and last["close"]<last["open"]:
            add(_candidate("supply_demand_retest","short",last["close"],base_hi+0.2*vol,rr,"fresh_supply_impulse_retest"))
    return result
