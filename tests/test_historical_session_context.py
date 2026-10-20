"""Offline causal session tests; no MT5 connection required."""
from datetime import datetime, timezone
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services"/"mt5-engine"))
from historical_session_context import build_prior_profiles, opening_ranges, range_for_bar

def bar(iso,price=100,volume=10):
    return {"time":int(datetime.fromisoformat(iso.replace("Z","+00:00")).timestamp()),
            "open":price,"high":price+0.1,"low":price-0.1,
            "close":price,"tick_volume":volume}

def test_prior_profile_only_previous_day():
    bars=[bar("2026-10-19T12:00:00Z",100),bar("2026-10-20T12:00:00Z",200)]
    profiles=build_prior_profiles(bars,0.1)
    assert datetime(2026,10,19).date() not in profiles
    assert profiles[datetime(2026,10,20).date()].poc<150

def test_london_opening_range_requires_all_three_bars_and_completed_window():
    bars=[bar("2026-10-20T07:00:00Z"),bar("2026-10-20T07:05:00Z"),
          bar("2026-10-20T07:10:00Z"),bar("2026-10-20T07:15:00Z")]
    ranges,session,zone,start=opening_ranges(bars,"EURUSD")
    assert range_for_bar(bars[2],ranges,session,zone,start) is None
    assert range_for_bar(bars[3],ranges,session,zone,start) is not None
    incomplete,_,_,_=opening_ranges(bars[:2],"EURUSD")
    assert not incomplete

def test_new_york_daylight_saving():
    # 09:30 EDT is 13:30 UTC on October 20.
    bars=[bar("2026-10-20T13:30:00Z"),bar("2026-10-20T13:35:00Z"),
          bar("2026-10-20T13:40:00Z"),bar("2026-10-20T13:45:00Z")]
    ranges,session,zone,start=opening_ranges(bars,"NAS100")
    assert range_for_bar(bars[3],ranges,session,zone,start) is not None
