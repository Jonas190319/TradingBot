from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional
from uuid import uuid4

from models import Direction, MarketSnapshot, Regime, TradeCandidate


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


CORE_STRATEGISTS: List[Strategist] = [
    OpeningRangeStrategist(),
    TrendPullbackStrategist(),
    CompressionBreakoutStrategist(),
    LiquiditySweepStrategist(),
]
