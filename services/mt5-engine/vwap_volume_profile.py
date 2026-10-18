"""Read-only intraday VWAP and prior-day tick-volume profile signal research.

Pure calculations: no MetaTrader connection, broker order calls, or network I/O.
Pass closed bars only, ordered oldest to newest. The caller determines broker-day
boundaries and feeds a completed prior session separately to avoid lookahead.
"""
from dataclasses import dataclass
from math import floor, isfinite
from typing import Sequence


@dataclass(frozen=True)
class Bar:
    high: float
    low: float
    close: float
    tick_volume: float


@dataclass(frozen=True)
class Profile:
    vah: float
    poc: float
    val: float
    total_volume: float


@dataclass(frozen=True)
class Signal:
    strategy: str
    side: str
    reference: float
    entry: float
    stop: float
    target: float
    rr: float


def _valid(bars: Sequence[Bar]) -> None:
    if not bars:
        raise ValueError("At least one closed bar required")
    for bar in bars:
        if not all(isfinite(v) for v in (bar.high, bar.low, bar.close, bar.tick_volume)):
            raise ValueError("Non-finite bar")
        if bar.high < bar.low or not bar.low <= bar.close <= bar.high or bar.tick_volume < 0:
            raise ValueError("Invalid OHLC or tick volume")


def vwap(bars: Sequence[Bar]) -> float:
    """Session VWAP using typical price and MT5 tick volume."""
    _valid(bars)
    volume = sum(b.tick_volume for b in bars)
    if volume <= 0:
        raise ValueError("No tick volume")
    return sum(((b.high + b.low + b.close) / 3) * b.tick_volume for b in bars) / volume


def volume_profile(prior_day_bars: Sequence[Bar], tick_size: float, value_area: float = 0.70) -> Profile:
    """Approximate prior-day profile: distribute each bar's tick volume evenly
    over the touched price bins. This is NOT exchange trade-at-price volume.
    """
    _valid(prior_day_bars)
    if not isfinite(tick_size) or tick_size <= 0 or not 0 < value_area <= 1:
        raise ValueError("Invalid tick size or value area")
    bins = {}
    for bar in prior_day_bars:
        if bar.tick_volume == 0:
            continue
        low_bin = floor((bar.low / tick_size) + 1e-9)
        high_bin = floor((bar.high / tick_size) + 1e-9)
        if high_bin - low_bin > 10000:
            raise ValueError("Excessive price bins: increase tick_size")
        allocation = bar.tick_volume / (high_bin - low_bin + 1)
        for index in range(low_bin, high_bin + 1):
            bins[index] = bins.get(index, 0.0) + allocation
    if not bins:
        raise ValueError("No prior-day tick volume")
    poc_bin = min(bins, key=lambda i: (-bins[i], i))
    total = sum(bins.values())
    selected = {poc_bin}
    accumulated = bins[poc_bin]
    left, right = poc_bin - 1, poc_bin + 1
    while accumulated < total * value_area:
        lv, rv = bins.get(left, 0.0), bins.get(right, 0.0)
        if lv <= 0 and rv <= 0:
            break
        if rv > lv:
            selected.add(right)
            accumulated += rv
            right += 1
        else:
            selected.add(left)
            accumulated += lv
            left -= 1
    return Profile(vah=round(max(selected) * tick_size, 10),
                   poc=round(poc_bin * tick_size, 10),
                   val=round(min(selected) * tick_size, 10),
                   total_volume=total)


def _signal(strategy: str, side: str, level: float, last: Bar,
            stop: float, rr: float) -> Signal | None:
    entry = last.close
    risk = entry - stop if side == "long" else stop - entry
    if risk <= 0:
        return None
    target = entry + rr * risk if side == "long" else entry - rr * risk
    return Signal(strategy, side, level, entry, stop, target, rr)


def detect_signals(today_closed: Sequence[Bar], prior_day: Profile,
                   touch_tolerance: float, rr: float = 2.0) -> list[Signal]:
    """Candidate setups from last two completed bars; no execution or position sizing.

    VWAP: touch/reclaim or touch/reject with a directional confirmation candle.
    Value area reversal: test VAH/VAL and close back inside the value area.
    Value area breakout: previous close inside, latest close beyond boundary
    with a confirming retest of that boundary.
    """
    _valid(today_closed)
    if len(today_closed) < 2:
        return []
    if not isfinite(touch_tolerance) or touch_tolerance < 0 or not isfinite(rr) or rr <= 0:
        raise ValueError("Invalid strategy parameters")
    previous, last = today_closed[-2:]
    current_vwap = vwap(today_closed)
    out = []
    if last.low <= current_vwap + touch_tolerance and last.close > current_vwap and last.close > previous.close:
        signal = _signal("VWAP_RETEST", "long", current_vwap, last, last.low - touch_tolerance, rr)
        if signal:
            out.append(signal)
    if last.high >= current_vwap - touch_tolerance and last.close < current_vwap and last.close < previous.close:
        signal = _signal("VWAP_RETEST", "short", current_vwap, last, last.high + touch_tolerance, rr)
        if signal:
            out.append(signal)
    if last.low <= prior_day.val + touch_tolerance and prior_day.val < last.close <= prior_day.vah:
        signal = _signal("VALUE_AREA_REVERSAL", "long", prior_day.val, last, last.low - touch_tolerance, rr)
        if signal:
            out.append(signal)
    if last.high >= prior_day.vah - touch_tolerance and prior_day.val <= last.close < prior_day.vah:
        signal = _signal("VALUE_AREA_REVERSAL", "short", prior_day.vah, last, last.high + touch_tolerance, rr)
        if signal:
            out.append(signal)
    if prior_day.val <= previous.close <= prior_day.vah and last.low <= prior_day.vah + touch_tolerance and last.close > prior_day.vah:
        signal = _signal("VALUE_AREA_BREAKOUT", "long", prior_day.vah, last, min(last.low, prior_day.vah - touch_tolerance), rr)
        if signal:
            out.append(signal)
    if prior_day.val <= previous.close <= prior_day.vah and last.high >= prior_day.val - touch_tolerance and last.close < prior_day.val:
        signal = _signal("VALUE_AREA_BREAKOUT", "short", prior_day.val, last, max(last.high, prior_day.val + touch_tolerance), rr)
        if signal:
            out.append(signal)
    return out
