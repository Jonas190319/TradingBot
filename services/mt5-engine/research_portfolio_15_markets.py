"""Proposed 15-market / six-strategy research configuration.

Configuration only. This module cannot submit orders or change the running Shadow bot.
All instruments and strategy rules require broker verification and backtesting.
"""
from dataclasses import dataclass

MARKETS = (
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "EURJPY",
    "NAS100", "US500", "US30", "GER40", "UK100",
    "XAUUSD", "XAGUSD", "USOIL", "UKOIL",
)

STRATEGIES = (
    "ema_pullback_rsi",
    "volume_profile_value_area_reversal",
    "opening_range_breakout_retest",
    "bollinger_rsi_mean_reversion",
    "volume_profile_breakout_adx",
    "supply_demand_retest",
)

@dataclass(frozen=True)
class ResearchCandidate:
    market: str
    strategy: str

def candidate_matrix():
    return tuple(ResearchCandidate(m, s) for m in MARKETS for s in STRATEGIES)

def validate_configuration():
    assert len(MARKETS) == len(set(MARKETS)) == 15
    assert len(STRATEGIES) == len(set(STRATEGIES)) == 6
    assert len(candidate_matrix()) == 90
    return True

# Initial hypotheses, NOT calibrated performance claims:
# supply_demand_retest: identify a short consolidation followed by a
# >=1.5 ATR impulse; only first retest of the origin zone is eligible;
# stop outside the zone plus ATR buffer, target >=2R or opposing structure;
# optionally use prior-session volume profile confluence as a testable filter.
# Prevent future-data leakage: confirm the impulse before marking the zone.
# Do not use this configuration for live/demo orders until validated.
