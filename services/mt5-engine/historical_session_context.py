"""Causal historical sessions for read-only research.

UTC calendar days for prior-day tick-volume profiles. Opening range uses
Europe/London 08:00-08:15 or America/New_York 09:30-09:45 local time.
These are explicit research conventions, not broker exchange sessions.
"""
from collections import defaultdict
from datetime import datetime, timezone, time
from zoneinfo import ZoneInfo
from vwap_volume_profile import Bar, volume_profile

def _date(bar, zone):
    return datetime.fromtimestamp(bar["time"], timezone.utc).astimezone(zone).date()

def _as_bar(b):
    return Bar(b["high"],b["low"],b["close"],b.get("tick_volume",0))

def build_prior_profiles(history, tick_size):
    """Profile keyed by UTC date, using only the previous populated UTC day."""
    groups=defaultdict(list)
    for b in history:
        groups[_date(b,timezone.utc)].append(b)
    profiles={}
    previous=None
    for day in sorted(groups):
        if previous is not None:
            try:
                profiles[day]=volume_profile([_as_bar(b) for b in groups[previous]],tick_size)
            except ValueError:
                pass
        previous=day
    return profiles

def opening_ranges(history, market):
    """Return range per (session-name, local date), only when all 3 M5 bars exist.

    MT5 timestamps denote bar OPEN. Caller must use only after 08:15 London
    or 09:45 New York respectively, with an already closed signal bar.
    """
    session="london" if market in ("EURUSD","GBPUSD","EURJPY","GER40","UK100") else "new_york"
    zone=ZoneInfo("Europe/London" if session=="london" else "America/New_York")
    start=time(8,0) if session=="london" else time(9,30)
    byday=defaultdict(list)
    for b in history:
        local=datetime.fromtimestamp(b["time"],timezone.utc).astimezone(zone)
        minutes=local.hour*60+local.minute
        s=start.hour*60+start.minute
        if s<=minutes<s+15 and minutes%5==0:
            byday[local.date()].append((minutes,b))
    result={}
    for day,items in byday.items():
        s=start.hour*60+start.minute
        lookup={minute:b for minute,b in items}
        if all(m in lookup for m in (s,s+5,s+10)):
            bars=[lookup[m] for m in (s,s+5,s+10)]
            result[(session,day)]=(max(b["high"] for b in bars),min(b["low"] for b in bars))
    return result,session,zone,start

def range_for_bar(bar, ranges, session, zone, start):
    local=datetime.fromtimestamp(bar["time"],timezone.utc).astimezone(zone)
    end=start.hour*60+start.minute+15
    # The signal bar closes five minutes after its open timestamp.
    if local.hour*60+local.minute+5<=end:
        return None
    return ranges.get((session,local.date()))
