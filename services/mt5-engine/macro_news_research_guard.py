"""Fail-closed economic-calendar guard; research only, no order calls."""
from datetime import timedelta, timezone

EXPOSURES = {
 "EURUSD":("EUR","USD"),"GBPUSD":("GBP","USD"),"USDJPY":("USD","JPY"),
 "AUDUSD":("AUD","USD"),"USDCAD":("USD","CAD"),"EURJPY":("EUR","JPY"),
 "NAS100":("USD",),"US500":("USD",),"US30":("USD",),"GER40":("EUR",),
 "UK100":("GBP",),"XAUUSD":("USD",),"XAGUSD":("USD",),
 "USOIL":("USD",),"UKOIL":("USD",),
}
def news_gate(symbol, now_utc, events, calendar_updated_utc,
              freshness_hours=12, before_minutes=30, after_minutes=15):
    """(allowed, reason, ids); stale/missing calendar blocks new entries."""
    if now_utc.tzinfo is None:
        raise ValueError("Timezone-aware now required")
    now=now_utc.astimezone(timezone.utc)
    if symbol not in EXPOSURES:
        return False,"unknown_market",()
    if calendar_updated_utc is None or calendar_updated_utc.tzinfo is None:
        return False,"calendar_unavailable",()
    age=now-calendar_updated_utc.astimezone(timezone.utc)
    if age>timedelta(hours=freshness_hours) or age<timedelta(minutes=-5):
        return False,"calendar_stale",()
    blocked=[]
    for e in events:
        if e.scheduled_utc.tzinfo is None:
            return False,"invalid_event_timestamp",()
        if e.currency.upper() not in EXPOSURES[symbol] or e.importance.lower() not in ("high","critical"):
            continue
        minutes=(e.scheduled_utc.astimezone(timezone.utc)-now).total_seconds()/60
        if -after_minutes<=minutes<=before_minutes:
            blocked.append(e.event_id)
    return (False,"high_impact_event",tuple(sorted(set(blocked)))) if blocked else (True,"clear",())
