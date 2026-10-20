"""Local append-only trade lifecycle journal for offline research.

Records signals, rejected candidates, pre-entry snapshots, open-bar updates,
exits and post-exit observations. No broker actions or remote uploads.
"""
from datetime import datetime,timezone
from pathlib import Path
import json
import math

PHASES=frozenset(("signal","rejected","entry","open","exit","post_exit"))
def write_event(path, *, trade_id, symbol, strategy, phase, observed_at_utc,
                values):
    if phase not in PHASES or not trade_id or not symbol or not strategy:
        raise ValueError("Invalid journal event")
    if observed_at_utc.tzinfo is None:
        raise ValueError("UTC-aware event timestamp required")
    if not isinstance(values,dict):
        raise TypeError("values must be a mapping")
    record={"trade_id":trade_id,"symbol":symbol,"strategy":strategy,
            "phase":phase,"observed_at_utc":observed_at_utc.astimezone(timezone.utc).isoformat(),
            "values":values}
    line=json.dumps(record,sort_keys=True,allow_nan=False,ensure_ascii=False)
    destination=Path(path)
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open("a",encoding="utf-8") as stream:
        stream.write(line+"\n")
    return record

def excursions(side,entry,stop,highs,lows):
    """MFE and MAE in initial-risk units for observed completed bars."""
    risk=abs(entry-stop)
    if risk<=0 or side not in ("long","short") or len(highs)!=len(lows) or not highs:
        raise ValueError("Invalid excursion inputs")
    if not all(math.isfinite(float(v)) for v in (entry,stop,*highs,*lows)):
        raise ValueError("Nonfinite prices")
    if side=="long":
        return max(0,(max(highs)-entry)/risk),max(0,(entry-min(lows))/risk)
    return max(0,(entry-min(lows))/risk),max(0,(max(highs)-entry)/risk)
