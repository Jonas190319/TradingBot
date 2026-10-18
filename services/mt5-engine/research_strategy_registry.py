"""Single source of truth for the 16 read-only research strategies and eight markets.

Inventory/coverage only: this module does not claim all strategies are integrated
into one runtime. No broker connection or order functions.
"""
from dataclasses import dataclass

MARKETS = ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "GER40", "NAS100", "US500", "US30")
EXISTING = (
    "opening_range", "trend_pullback", "compression_breakout",
    "liquidity_sweep", "supply_demand", "range_trading",
    "vwap_reclaim", "mean_reversion", "harmonic_gartley",
    "harmonic_bat", "harmonic_butterfly", "harmonic_crab", "harmonic_shark",
)
NEW = ("VWAP_RETEST", "VALUE_AREA_REVERSAL", "VALUE_AREA_BREAKOUT")
STRATEGIES = EXISTING + NEW


@dataclass(frozen=True)
class Coverage:
    market: str
    strategy: str
    engine: str


def coverage_matrix():
    return tuple(
        Coverage(market, strategy, "shadow" if strategy in EXISTING else "profile_scanner")
        for market in MARKETS for strategy in STRATEGIES
    )


def validate_inventory(shadow_names, profile_names, market_names):
    """Fail closed when the actual engines diverge from the expected inventory."""
    expected = (set(EXISTING), set(NEW), set(MARKETS))
    actual = (set(shadow_names), set(profile_names), set(market_names))
    if actual != expected:
        missing = [sorted(e - a) for e, a in zip(expected, actual)]
        extra = [sorted(a - e) for e, a in zip(expected, actual)]
        raise ValueError(f"Strategy inventory mismatch: missing={missing}, extra={extra}")
    return coverage_matrix()
