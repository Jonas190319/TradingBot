from datetime import datetime, timedelta, timezone

import pytest

from broker_clock import timestamp_utc, closed_history_mode
from market_features import bars_from_rates
from test_shadow import Database, load_bridge


def epoch(text):
    return datetime.fromisoformat(text + '+00:00').timestamp()


@pytest.mark.parametrize('server,utc', [
    ('2026-10-08T23:31:53', '2026-10-08T20:31:53'),
    ('2026-01-08T22:31:53', '2026-01-08T20:31:53'),
    # US and European DST transition dates differ; never use Europe/Berlin.
    ('2026-03-10T15:00:00', '2026-03-10T12:00:00'),
    ('2026-10-28T15:00:00', '2026-10-28T12:00:00'),
    ('2026-11-03T14:00:00', '2026-11-03T12:00:00'),
])
def test_pepperstone_server_to_utc(server, utc):
    assert timestamp_utc(epoch(server), 'pepperstone_server').timestamp() == epoch(utc)


def test_millisecond_precision_and_utc_identity():
    raw = epoch('2026-10-08T23:31:53') + .123
    assert timestamp_utc(raw, 'pepperstone_server').timestamp() == pytest.approx(raw-10800)
    assert timestamp_utc(raw, 'utc').timestamp() == pytest.approx(raw)


@pytest.mark.parametrize('value', [0, -1, float('nan'), float('inf')])
def test_invalid_timestamp_rejected(value):
    with pytest.raises(ValueError): timestamp_utc(value, 'utc')


@pytest.mark.parametrize('wall', ['2026-03-08T09:30:00','2026-11-01T08:30:00'])
def test_dst_ambiguous_or_nonexistent_wall_time_rejected(wall):
    with pytest.raises(ValueError, match='DST'): timestamp_utc(epoch(wall), 'pepperstone_server')


@pytest.mark.parametrize('hours,expected', [(0,'utc'),(3,'pepperstone_server')])
def test_history_basis_identified_before_future_filter(hours,expected):
    now=datetime(2026,10,8,20,35,tzinfo=timezone.utc)
    times=[now-timedelta(minutes=5*i)+timedelta(hours=hours) for i in range(60,0,-1)]
    rates=[dict(time=t.timestamp(),open=100,high=101,low=99,close=100,tick_volume=50) for t in times]
    mode=closed_history_mode(rates,now)
    assert mode == expected
    normalized=bars_from_rates(rates,now,mode)
    assert len(normalized)==60 and normalized[-1].ts == now-timedelta(minutes=5)


def test_auto_basis_does_not_freshen_stale_closed_history():
    now=datetime(2026,10,8,20,35,tzinfo=timezone.utc)
    rates=[dict(time=(now-timedelta(hours=1)).timestamp())]
    with pytest.raises(ValueError,match='unique fresh'): closed_history_mode(rates,now)


@pytest.mark.parametrize('age,accepted', [(2,True),(-.5,True),(-120,False),(120,False),(1922,False)])
def test_observed_server_ticks_corrected_without_bypassing_freshness(monkeypatch,age,accepted):
    from types import SimpleNamespace
    bridge,mt5=load_bridge(monkeypatch)
    now=datetime.now(timezone.utc)
    # Derive the documented offset from today's US DST, not the machine locale.
    from zoneinfo import ZoneInfo
    offset=timedelta(hours=7)+now.astimezone(ZoneInfo('America/New_York')).utcoffset()
    raw=now.timestamp()+offset.total_seconds()-age
    mt5.symbol_info=lambda symbol:SimpleNamespace(point=.01)
    mt5.symbol_info_tick=lambda symbol:SimpleNamespace(bid=100,ask=100.02,time_msc=raw*1000)
    db=Database()
    result=bridge.publish_tick(db,'EURUSD','EURUSD',60,'pepperstone_server')
    assert (result is not None) == accepted
    if accepted:
        row=db.rows['market_context'][0]
        assert row['technical_context']['timestamp_mode']=='pepperstone_server'
        assert abs(datetime.fromisoformat(row['ts']).timestamp()-(now.timestamp()-age))<.001
