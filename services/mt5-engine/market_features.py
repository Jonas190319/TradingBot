"""Closed M5 bar features. Scores are research heuristics, not probabilities."""
from datetime import datetime, time, timedelta, timezone
from math import isfinite
from statistics import mean
from zoneinfo import ZoneInfo

from services.agent_team.models import Bar
from broker_clock import timestamp_utc
from supply_demand import zone_features
from harmonic_features import harmonic_features

BAR_SECONDS = 300
MIN_BARS = 60
SESSION_TEMPLATES = {
    'GER40': ('Europe/Berlin', time(9, 0)),
    'NAS100': ('America/New_York', time(9, 30)),
    'US500': ('America/New_York', time(9, 30)),
    'US30': ('America/New_York', time(9, 30)),
    'XAUUSD': ('America/New_York', time(8, 20)),
}


def clip(value):
    return max(0.0, min(100.0, float(value)))


def bars_from_rates(rates, now, time_mode='utc'):
    if rates is None:
        return ()
    rows = []
    for rate in rates:
        ts = timestamp_utc(rate['time'], time_mode)
        if ts + timedelta(seconds=BAR_SECONDS) > now:
            continue  # Never feed a forming bar to the decision stack.
        values = [float(rate[k]) for k in ('open', 'high', 'low', 'close')]
        if not all(isfinite(x) and x > 0 for x in values):
            raise ValueError('Non-finite or non-positive OHLC')
        op, hi, lo, close = values
        if hi < max(op, close, lo) or lo > min(op, close):
            raise ValueError('Invalid OHLC envelope')
        volume = float(rate['tick_volume'])
        if not isfinite(volume) or volume < 0:
            raise ValueError('Invalid tick volume')
        rows.append(Bar(ts, op, hi, lo, close, volume))
    if any(a.ts >= b.ts for a, b in zip(rows, rows[1:])):
        raise ValueError('History timestamps are duplicated or out of order')
    return tuple(rows)


def opening_range(symbol, now, bars):
    zone, start = SESSION_TEMPLATES.get(symbol, ('Europe/London', time(8, 0)))
    local = now.astimezone(ZoneInfo(zone))
    opened = datetime.combine(local.date(), start, tzinfo=ZoneInfo(zone)).astimezone(timezone.utc)
    end = opened + timedelta(minutes=15)
    # Cash-opening templates, not broker trading hours. No holiday calendar yet.
    if local.weekday() >= 5 or not end <= now <= end + timedelta(hours=2):
        return {'session': zone, 'or_ready': False}
    sample = [b for b in bars if opened <= b.ts < end]
    expected = [opened + timedelta(minutes=5*i) for i in range(3)]
    if [b.ts for b in sample] != expected:
        return {'session': zone, 'or_ready': False}
    return {'session': zone, 'or_ready': True,
            'or_high': max(b.high for b in sample), 'or_low': min(b.low for b in sample),
            'or_start_utc': opened.isoformat(), 'or_end_utc': end.isoformat()}


def build_features(symbol, now, bars):
    if len(bars) < MIN_BARS:
        raise ValueError(f'Need {MIN_BARS} closed M5 bars; got {len(bars)}')
    if not 0 <= (now - bars[-1].ts).total_seconds() <= 2 * BAR_SECONDS:
        raise ValueError('Closed bar history is stale or from the future')
    if any((b.ts-a.ts).total_seconds() != BAR_SECONDS for a, b in zip(bars[-60:], bars[-59:])):
        raise ValueError('Recent M5 history contains gaps')
    tr, plus, minus = [], [], []
    for prev, cur in zip(bars, bars[1:]):
        tr.append(max(cur.high-cur.low, abs(cur.high-prev.close), abs(cur.low-prev.close)))
        up, down = cur.high-prev.high, prev.low-cur.low
        plus.append(up if up > down and up > 0 else 0.0)
        minus.append(down if down > up and down > 0 else 0.0)
    atr = mean(tr[-14:])
    if atr <= 0:
        raise ValueError('ATR is zero')
    dx = []
    for end in range(len(tr)-13, len(tr)+1):
        start = max(0, end-14)
        p, m = sum(plus[start:end]), sum(minus[start:end])
        dx.append(100*abs(p-m)/(p+m) if p+m else 0)
    adx = mean(dx)
    closes = [b.close for b in bars]
    fast, slow = mean(closes[-10:]), mean(closes[-30:])
    last, prev = bars[-1], bars[-2]
    bias = 1 if fast > slow else -1 if fast < slow else 0
    momentum = (last.close-closes[-6])/atr
    prior = bars[-21:-1]
    recent_high, recent_low = max(b.high for b in prior), min(b.low for b in prior)
    compressed = mean(tr[-11:-1]) / max(mean(tr[-41:-11]), 1e-12)
    expansion = tr[-1] / max(mean(tr[-11:-1]), 1e-12)
    break_bias = 1 if last.close > recent_high else -1 if last.close < recent_low else 0
    sweep_side = 1 if last.high > recent_high and last.close < recent_high else -1 if last.low < recent_low and last.close > recent_low else 0
    span = max(last.high-last.low, 1e-12)
    wick = (last.high-max(last.open,last.close))/span if sweep_side > 0 else (min(last.open,last.close)-last.low)/span
    # Require an observed pullback and recovery instead of generating on every trend bar.
    pullback = (bias > 0 and prev.low <= fast and last.close > prev.close) or (bias < 0 and prev.high >= fast and last.close < prev.close)
    vol_base = mean(b.volume for b in prior)
    f = dict(atr=atr, adx=adx, trend_bias=bias if pullback else 0,
             trend_alignment=clip(50+abs(fast-slow)/atr*25),
             momentum_score=clip(50+abs(momentum)*20), momentum_turn=clip(50+abs(last.close-prev.close)/atr*40),
             momentum_flip=clip(50+abs(last.close-last.open)/atr*30),
             structure_score=clip(50+abs(fast-slow)/atr*20),
             pullback_quality=clip(100-abs(last.close-fast)/atr*35) if pullback else 0,
             compression_score=clip((1-compressed)*150), expansion_score=clip(expansion*50),
             breakout_bias=break_bias, sweep_side=sweep_side,
             sweep_score=clip(55+abs((last.high-recent_high) if sweep_side > 0 else (recent_low-last.low))/atr*45) if sweep_side else 0,
             rejection_score=clip(wick*100) if sweep_side else 0,
             volume_score=clip(last.volume/vol_base*50) if vol_base else 0,
             retest_quality=0, opening_range_quality=0,
             score_method='heuristic-v1-not-calibrated', bar_ts=last.ts.isoformat(),
             tick_volume_is_proxy=True)
    # All boundaries use prior closed candles, excluding the signal candle.
    f['range_high'] = recent_high
    f['range_low'] = recent_low
    f['last_open'] = last.open
    f['last_close'] = last.close
    f['mean_deviation_atr'] = (last.close - slow) / atr
    f['reversal_direction'] = (1 if last.close > last.open and prev.close < prev.open
                               else -1 if last.close < last.open and prev.close > prev.open else 0)
    # Tick-volume-weighted typical price, reset at UTC day boundary. Proxy, not exchange VWAP.
    session_bars = [b for b in bars if b.ts.date() == last.ts.date()]
    total_volume = sum(b.volume for b in session_bars)
    f['vwap_ready'] = len(session_bars) >= 5 and total_volume > 0
    f['vwap_session'] = last.ts.date().isoformat()
    f['session_vwap'] = (sum(((b.high + b.low + b.close) / 3) * b.volume for b in session_bars)
                         / total_volume) if f['vwap_ready'] else None
    f['vwap_reclaim_side'] = None
    if f['vwap_ready']:
        vwap = f['session_vwap']
        if prev.close < vwap < last.close and last.close > last.open:
            f['vwap_reclaim_side'] = 'long'
        elif prev.close > vwap > last.close and last.close < last.open:
            f['vwap_reclaim_side'] = 'short'
    f.update(zone_features(bars, atr))
    f.update(harmonic_features(bars, atr))
    f.update(opening_range(symbol, now, bars))
    if f['or_ready']:
        width = f['or_high']-f['or_low']
        f['opening_range_quality'] = clip(100-abs(width/atr-1.5)*25)
        # Only observed retests earn a retest score; a fresh breakout gets zero.
        touched = (last.low <= f['or_high'] <= last.high and last.close > f['or_high']) or (last.low <= f['or_low'] <= last.high and last.close < f['or_low'])
        f['retest_quality'] = 80 if touched else 0
    return f
