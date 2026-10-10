from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional
from uuid import uuid4

from .models import Direction, MarketSnapshot, Regime, TradeCandidate


def _f(features: Dict[str, object], key: str, default: float = 0.0) -> float:
    value = features.get(key, default)
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _clip(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


class Strategist:
    name = "base"

    def evaluate(self, snap: MarketSnapshot, regime: Regime) -> Optional[TradeCandidate]:
        raise NotImplementedError

    def _candidate(
        self,
        snap: MarketSnapshot,
        regime: Regime,
        direction: Direction,
        score: float,
        entry: float,
        stop: float,
        tp1: float,
        tp2: Optional[float],
        invalidation: str,
        evidence: Dict[str, object],
    ) -> TradeCandidate:
        return TradeCandidate(
            candidate_id=f"{self.name}-{uuid4().hex[:12]}",
            created_at=snap.ts,
            symbol=snap.symbol,
            strategy=self.name,
            direction=direction,
            entry=entry,
            stop_loss=stop,
            take_profit_1=tp1,
            take_profit_2=tp2,
            setup_score=_clip(score),
            regime=regime,
            invalidation=invalidation,
            management_plan={
                "at_0_8R": "hold unless structure invalidates",
                "at_1_0R": "consider partial only if momentum weakens",
                "at_tp1": "take 25-35% and trail by structure",
                "risk_increase_after_entry": False,
            },
            evidence=evidence,
            valid_until=snap.ts + timedelta(minutes=45),
        )


class OpeningRangeStrategist(Strategist):
    name = "opening_range"

    def evaluate(self, snap: MarketSnapshot, regime: Regime) -> Optional[TradeCandidate]:
        f = snap.features
        or_high, or_low = _f(f, "or_high"), _f(f, "or_low")
        if not or_high or not or_low or or_high <= or_low:
            return None
        price, atr = snap.mid, max(_f(f, "atr"), (or_high - or_low) / 2)
        momentum = _f(f, "momentum_score", 50)
        retest = _f(f, "retest_quality", 50)
        volume = _f(f, "volume_score", 50)
        trend = _f(f, "trend_alignment", 50)
        range_quality = _f(f, "opening_range_quality", 50)
        score = 0.28 * momentum + 0.22 * retest + 0.18 * volume + 0.17 * trend + 0.15 * range_quality
        if price > or_high:
            direction = Direction.LONG
            entry = price
            stop = min(or_high - 0.15 * atr, entry - 0.7 * atr)
            risk = entry - stop
            return self._candidate(snap, regime, direction, score, entry, stop, entry + 1.6*risk, entry + 2.4*risk,
                                   "close back inside opening range with failed retest",
                                   {"or_high": or_high, "or_low": or_low, "breakout_side": "high"})
        if price < or_low:
            direction = Direction.SHORT
            entry = price
            stop = max(or_low + 0.15 * atr, entry + 0.7 * atr)
            risk = stop - entry
            return self._candidate(snap, regime, direction, score, entry, stop, entry - 1.6*risk, entry - 2.4*risk,
                                   "close back inside opening range with failed retest",
                                   {"or_high": or_high, "or_low": or_low, "breakout_side": "low"})
        return None


class TrendPullbackStrategist(Strategist):
    name = "trend_pullback"

    def evaluate(self, snap: MarketSnapshot, regime: Regime) -> Optional[TradeCandidate]:
        f = snap.features
        trend = _f(f, "trend_alignment", 50)
        pullback = _f(f, "pullback_quality", 50)
        momentum = _f(f, "momentum_turn", 50)
        structure = _f(f, "structure_score", 50)
        adx = _f(f, "adx", 20)
        bias = _f(f, "trend_bias", 0)
        score = 0.30*trend + 0.25*pullback + 0.20*momentum + 0.15*structure + 0.10*_clip(adx*2)
        if abs(bias) < 0.25 or regime not in {Regime.TREND, Regime.HIGH_VOL, Regime.BREAKOUT}:
            return None
        atr = max(_f(f, "atr"), snap.spread * 20)
        entry = snap.mid
        if bias > 0:
            stop = entry - 0.9*atr
            risk = entry - stop
            return self._candidate(snap, regime, Direction.LONG, score, entry, stop, entry+1.7*risk, entry+2.6*risk,
                                   "higher-timeframe structure breaks or momentum fails to recover",
                                   {"trend_bias": bias, "adx": adx})
        stop = entry + 0.9*atr
        risk = stop - entry
        return self._candidate(snap, regime, Direction.SHORT, score, entry, stop, entry-1.7*risk, entry-2.6*risk,
                               "higher-timeframe structure breaks or momentum fails to recover",
                               {"trend_bias": bias, "adx": adx})


class CompressionBreakoutStrategist(Strategist):
    name = "compression_breakout"

    def evaluate(self, snap: MarketSnapshot, regime: Regime) -> Optional[TradeCandidate]:
        f = snap.features
        compression = _f(f, "compression_score", 50)
        expansion = _f(f, "expansion_score", 50)
        momentum = _f(f, "momentum_score", 50)
        volume = _f(f, "volume_score", 50)
        side = _f(f, "breakout_bias", 0)
        score = 0.35*compression + 0.30*expansion + 0.20*momentum + 0.15*volume
        if abs(side) < 0.2 or compression < 55 or expansion < 50:
            return None
        atr = max(_f(f, "atr"), snap.spread * 20)
        entry = snap.mid
        if side > 0:
            stop = entry - 0.8*atr
            risk = entry-stop
            return self._candidate(snap, regime, Direction.LONG, score, entry, stop, entry+1.8*risk, entry+2.8*risk,
                                   "price re-enters compression zone and expansion collapses",
                                   {"compression": compression, "expansion": expansion})
        stop = entry + 0.8*atr
        risk = stop-entry
        return self._candidate(snap, regime, Direction.SHORT, score, entry, stop, entry-1.8*risk, entry-2.8*risk,
                               "price re-enters compression zone and expansion collapses",
                               {"compression": compression, "expansion": expansion})


class LiquiditySweepStrategist(Strategist):
    name = "liquidity_sweep"

    def evaluate(self, snap: MarketSnapshot, regime: Regime) -> Optional[TradeCandidate]:
        f = snap.features
        sweep = _f(f, "sweep_score", 50)
        rejection = _f(f, "rejection_score", 50)
        structure = _f(f, "structure_score", 50)
        momentum_flip = _f(f, "momentum_flip", 50)
        side = _f(f, "sweep_side", 0)  # +1 swept highs => short, -1 swept lows => long
        score = 0.35*sweep + 0.30*rejection + 0.20*structure + 0.15*momentum_flip
        if abs(side) < 0.25 or sweep < 55 or rejection < 55:
            return None
        atr = max(_f(f, "atr"), snap.spread * 20)
        entry = snap.mid
        if side > 0:
            stop = entry + 0.75*atr
            risk = stop-entry
            return self._candidate(snap, regime, Direction.SHORT, score, entry, stop, entry-1.6*risk, entry-2.3*risk,
                                   "price accepts above swept liquidity level",
                                   {"sweep_side": "highs", "rejection": rejection})
        stop = entry - 0.75*atr
        risk = entry-stop
        return self._candidate(snap, regime, Direction.LONG, score, entry, stop, entry+1.6*risk, entry+2.3*risk,
                               "price accepts below swept liquidity level",
                               {"sweep_side": "lows", "rejection": rejection})



class SupplyDemandStrategist(Strategist):
    """Trade only a confirmed closed-candle rejection of an established zone."""
    name = "supply_demand"

    def evaluate(self, snap: MarketSnapshot, regime: Regime) -> Optional[TradeCandidate]:
        f = snap.features
        if not f.get("sd_zone_present") or not f.get("sd_zone_reaction"):
            return None
        side = f.get("sd_zone_side")
        if side not in {"demand", "supply"}:
            return None
        lower, upper = _f(f, "sd_zone_lower"), _f(f, "sd_zone_upper")
        atr = max(_f(f, "atr"), snap.spread * 20)
        if not (0 < lower < upper and atr > 0):
            return None
        direction = Direction.LONG if side == "demand" else Direction.SHORT
        entry = snap.mid
        stop = min(lower - 0.15 * atr, entry - 0.7 * atr) if side == "demand" else max(upper + 0.15 * atr, entry + 0.7 * atr)
        risk = abs(entry - stop)
        if risk <= snap.spread * 3 or risk > atr * 3:
            return None
        touches = _f(f, "sd_zone_touches")
        score = _clip(60 + min(_f(f, "sd_zone_departure_atr"), 3) * 5 - max(0, touches - 1) * 8)
        evidence = {"zone_side": side, "lower": lower, "upper": upper,
                    "origin_ts": f.get("sd_zone_origin_ts"), "confirmed_ts": f.get("sd_zone_confirmed_ts"),
                    "touches": touches, "method": f.get("sd_method"), "sampled": True}
        sign = 1 if side == "demand" else -1
        return self._candidate(snap, regime, direction, score, entry, stop,
                               entry + sign * 1.6 * risk, entry + sign * 2.4 * risk,
                               "confirmed close through the opposite side of the zone", evidence)


class RangeTradingStrategist(Strategist):
    """Range bounce with closed-bar rejection; no blind limit orders."""
    name = "range_trading"

    def evaluate(self, snap: MarketSnapshot, regime: Regime) -> Optional[TradeCandidate]:
        f = snap.features
        if regime != Regime.RANGE:
            return None
        high, low, atr = _f(f, "range_high"), _f(f, "range_low"), _f(f, "atr")
        close, prev = _f(f, "last_close"), _f(f, "last_open")
        if not (high > low > 0 and atr > 0 and high - low >= 2 * atr):
            return None
        entry = snap.mid
        if low <= close <= low + 0.3 * atr and close > prev:
            stop = low - 0.3 * atr
            direction = Direction.LONG
            sign = 1
        elif high - 0.3 * atr <= close <= high and close < prev:
            stop = high + 0.3 * atr
            direction = Direction.SHORT
            sign = -1
        else:
            return None
        risk = abs(entry - stop)
        if risk <= snap.spread * 3 or risk > atr * 2:
            return None
        return self._candidate(snap, regime, direction, 62, entry, stop,
                               entry + sign * 1.5 * risk, entry + sign * 2.2 * risk,
                               "range boundary broken on closed candle",
                               {"range_low": low, "range_high": high, "confirmation": "closed-bar rejection"})


class VWAPReclaimStrategist(Strategist):
    """Research only; requires a session VWAP and explicit tick-volume provenance."""
    name = "vwap_reclaim"

    def evaluate(self, snap: MarketSnapshot, regime: Regime) -> Optional[TradeCandidate]:
        f = snap.features
        if not f.get("vwap_ready") or not f.get("vwap_reclaim_side"):
            return None
        side = f.get("vwap_reclaim_side")
        if side not in {"long", "short"}:
            return None
        atr = max(_f(f, "atr"), snap.spread * 20)
        if atr <= 0:
            return None
        sign = 1 if side == "long" else -1
        entry = snap.mid
        stop = entry - sign * atr
        return self._candidate(snap, regime, Direction.LONG if sign == 1 else Direction.SHORT,
                               60, entry, stop, entry + sign * 1.6 * atr, entry + sign * 2.4 * atr,
                               "session VWAP reclaim fails",
                               {"vwap": f.get("session_vwap"), "volume_proxy": "tick_volume",
                                "session": f.get("vwap_session")})


class MeanReversionStrategist(Strategist):
    """Low-priority experiment; requires observed stretch and reversal."""
    name = "mean_reversion"

    def evaluate(self, snap: MarketSnapshot, regime: Regime) -> Optional[TradeCandidate]:
        f = snap.features
        if regime != Regime.RANGE:
            return None
        deviation, atr = _f(f, "mean_deviation_atr"), _f(f, "atr")
        reversal = _f(f, "reversal_direction")
        if atr <= 0 or abs(deviation) < 2 or reversal == 0 or deviation * reversal >= 0:
            return None
        sign = 1 if reversal > 0 else -1
        entry = snap.mid
        stop = entry - sign * atr
        return self._candidate(snap, regime, Direction.LONG if sign > 0 else Direction.SHORT,
                               50, entry, stop, entry + sign * 1.3 * atr, entry + sign * 2 * atr,
                               "mean reversion rejection failed",
                               {"deviation_atr": deviation, "research_priority": "low"})


class HarmonicPatternStrategist(Strategist):
    """One independent shadow strategy per pattern, with confirmed pivot evidence."""
    def __init__(self, pattern: str):
        if pattern not in {"gartley", "bat", "butterfly", "crab", "shark"}:
            raise ValueError("Unknown harmonic pattern")
        self.pattern = pattern
        self.name = "harmonic_" + pattern

    def evaluate(self, snap: MarketSnapshot, regime: Regime) -> Optional[TradeCandidate]:
        f = snap.features
        if not f.get("harmonic_ready"):
            return None
        match = next((m for m in f.get("harmonic_matches", [])
                      if m.get("pattern") == self.pattern), None)
        if not match or match.get("direction") not in {"long", "short"}:
            return None
        atr = max(_f(f, "atr"), snap.spread * 20)
        if atr <= 0:
            return None
        sign = 1 if match["direction"] == "long" else -1
        pivot = float(match["pivot_price"])
        entry = snap.mid
        stop = min(pivot - 0.2 * atr, entry - 0.7 * atr) if sign > 0 else max(pivot + 0.2 * atr, entry + 0.7 * atr)
        risk = abs(entry - stop)
        if risk <= snap.spread * 3 or risk > atr * 3:
            return None
        zone_side = "demand" if sign > 0 else "supply"
        confluence = bool(f.get("sd_zone_present") and f.get("sd_zone_side") == zone_side)
        score = 62 + (8 if confluence else 0)
        return self._candidate(snap, regime, Direction.LONG if sign > 0 else Direction.SHORT,
                               score, entry, stop, entry + sign * 1.5 * risk,
                               entry + sign * 2.3 * risk,
                               "confirmed pattern pivot invalidated",
                               {"pattern": self.pattern, "confirmed_pivot": match,
                                "supply_demand_confluence": confluence,
                                "heuristic_not_win_probability": True})


CORE_STRATEGISTS: List[Strategist] = [
    OpeningRangeStrategist(),
    TrendPullbackStrategist(),
    CompressionBreakoutStrategist(),
    LiquiditySweepStrategist(),
    SupplyDemandStrategist(),
    RangeTradingStrategist(),
    VWAPReclaimStrategist(),
    MeanReversionStrategist(),
    HarmonicPatternStrategist('gartley'),
    HarmonicPatternStrategist('bat'),
    HarmonicPatternStrategist('butterfly'),
    HarmonicPatternStrategist('crab'),
    HarmonicPatternStrategist('shark'),
]
