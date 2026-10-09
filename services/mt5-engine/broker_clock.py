"""Explicit MT5 timestamp conversion; never infer an offset from a stale quote.

Pepperstone wall clock is New York + seven hours (GMT+2/+3 following US DST).
MetaQuotes documents UTC, so a separate UTC mode remains available. This demo
terminal's observed ticks encode server wall time in epoch-shaped values.
"""
from datetime import datetime, timedelta, timezone
from math import isfinite
from zoneinfo import ZoneInfo


def timestamp_utc(seconds, mode='utc'):
    seconds = float(seconds)
    if not isfinite(seconds) or seconds <= 0:
        raise ValueError('Invalid MT5 timestamp')
    stamp = datetime.fromtimestamp(seconds, timezone.utc)
    if mode == 'utc':
        return stamp
    if mode != 'pepperstone_server':
        raise ValueError('Unsupported MT5 timestamp mode')
    # Interpret the epoch-shaped value as a wall-clock label, not a UTC instant.
    ny_wall = stamp.replace(tzinfo=None) - timedelta(hours=7)
    ny_zone = ZoneInfo('America/New_York')
    first = ny_wall.replace(tzinfo=ny_zone, fold=0)
    second = ny_wall.replace(tzinfo=ny_zone, fold=1)
    if first.utcoffset() != second.utcoffset():
        raise ValueError('Ambiguous/nonexistent Pepperstone DST transition timestamp')
    return first.astimezone(timezone.utc)


def closed_history_mode(rates, now, mode='auto'):
    if mode != 'auto':
        if mode not in {'utc', 'pepperstone_server'}:
            raise ValueError('Unsupported MT5 bar timestamp mode')
        return mode
    if rates is None or len(rates) == 0:
        raise ValueError('MT5 returned no closed M5 history')
    # Check the actual latest returned bar BEFORE filtering forming/future bars.
    # Otherwise a future-shifted history could appear fresh after truncation.
    latest = rates[-1]['time']
    plausible = []
    for choice in ('utc', 'pepperstone_server'):
        ts = timestamp_utc(latest, choice)
        if 0 <= (now-ts).total_seconds() <= 600:
            plausible.append(choice)
    if len(plausible) != 1:
        raise ValueError('Cannot establish a unique fresh M5 timestamp basis')
    return plausible[0]
