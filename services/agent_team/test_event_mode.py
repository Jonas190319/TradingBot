from datetime import datetime, timedelta, timezone

from .event_mode import EventMode, ReactionTracker
from .models import Direction, EconomicEvent, MarketSnapshot


def market(ts, symbol="EURUSD", bid=1.1, ask=1.1002):
    return MarketSnapshot(symbol=symbol, ts=ts, bid=bid, ask=ask, spread_points=2)


def test_high_impact_event_enters_pre_news_mode():
    now = datetime(2026, 9, 16, 12, 25, tzinfo=timezone.utc)
    event = EconomicEvent(now + timedelta(minutes=3), "USD", "CPI YoY", 3, consensus=2.8, previous=2.7)
    result = EventMode().assess(market(now), [event])
    assert result.active
    assert result.phase == "pre_news"
    assert result.direction == Direction.NO_TRADE


def test_actual_vs_consensus_creates_fx_macro_impulse():
    ts = datetime(2026, 9, 16, 12, 30, tzinfo=timezone.utc)
    event = EconomicEvent(ts, "USD", "CPI YoY", 3, actual=3.1, consensus=2.8, previous=2.7)
    result = EventMode().assess(market(ts + timedelta(seconds=1), "EURUSD"), [event])
    assert result.phase == "post_news"
    assert result.surprise is not None and result.surprise > 0
    assert result.direction == Direction.SHORT  # USD is EURUSD quote currency


def test_missing_actual_fails_closed_at_release():
    ts = datetime(2026, 9, 16, 12, 30, tzinfo=timezone.utc)
    event = EconomicEvent(ts, "USD", "Nonfarm Payrolls", 3, consensus=150, previous=140)
    result = EventMode().assess(market(ts + timedelta(seconds=1)), [event])
    assert result.phase == "await_actual"
    assert result.direction == Direction.NO_TRADE


def test_reaction_tracker_records_fixed_checkpoint():
    ts = datetime(2026, 9, 16, 12, 30, tzinfo=timezone.utc)
    event = EconomicEvent(ts, "USD", "CPI YoY", 3, actual=3.1, consensus=2.8)
    tracker = ReactionTracker()
    tracker.anchor(event, market(ts - timedelta(seconds=1), bid=1.1, ask=1.1))
    observations = tracker.observe(event, market(ts + timedelta(seconds=5), bid=1.099, ask=1.099))
    assert len(observations) == 1
    assert observations[0].seconds_after == 5
    assert observations[0].return_bps is not None and observations[0].return_bps < 0
