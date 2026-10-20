"""Read-only indicator, market-regime and economic-event tracking schema.

Research data contract only; no external news feed, order placement, scheduler,
database migration or automated strategy adaptation is activated here.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple

INDICATORS = (
    "ema20", "ema50", "ema200", "rsi14", "macd_hist",
    "adx14", "plus_di14", "minus_di14", "atr14",
    "bb_width20", "poc", "vah", "val",
)
TIMEFRAMES = ("M5", "M15", "H1", "H4")
EVENT_WINDOWS_MIN = (-60, -30, -15, -5, 0, 5, 15, 30, 60)

@dataclass(frozen=True)
class IndicatorObservation:
    symbol: str
    timeframe: str
    candle_close_utc: datetime
    indicator: str
    value: float
    previous_value: Optional[float]
    slope_3: Optional[float]
    price_close: float
    market_regime: str
    source: str = "mt5_completed_bar"

@dataclass(frozen=True)
class EconomicEvent:
    event_id: str
    scheduled_utc: datetime
    currency: str
    name: str
    importance: str
    forecast: Optional[float] = None
    actual: Optional[float] = None
    previous: Optional[float] = None
    source: str = ""
    published_at_utc: Optional[datetime] = None

@dataclass(frozen=True)
class TradeObservation:
    trade_id: str
    symbol: str
    strategy: str
    observed_at_utc: datetime
    phase: str  # pre_signal, entry, open, exit, post_exit, rejected
    entry: Optional[float]
    stop: Optional[float]
    target: Optional[float]
    mae_r: Optional[float]
    mfe_r: Optional[float]
    news_event_ids: Tuple[str, ...] = ()

def validate_indicator_observation(item: IndicatorObservation):
    if item.timeframe not in TIMEFRAMES or item.indicator not in INDICATORS:
        raise ValueError("Unsupported timeframe or indicator")
    if item.candle_close_utc.tzinfo is None:
        raise ValueError("UTC-aware timestamps required")
    return True

# Causality: only completed candles and event values published by the
# observation timestamp may be used in decisions/backtests. Forecast and
# actual values must be versioned separately; avoid look-ahead leakage.
# Track rejected signals, spread/slippage, and 12/24/48 post-exit M5 bars.
# News policy should fail closed when calendar freshness cannot be verified.
# Performance comparisons require sufficient sample sizes and out-of-sample
# tests. Correlation is not proof of predictive causality.
