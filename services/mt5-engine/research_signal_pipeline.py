"""Research-only pipeline connecting six strategy signals with candle, EMA, news and journal.

No MT5 connection, order placement, scheduler or remote uploads.
Caller supplies *completed* chronological candles and fresh sourced calendar data.
"""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from six_strategy_signal_engine import scan, ema, atr
from ema_geometry_features import ema_geometry
from candlestick_pattern_tracker import latest_pattern_features
from macro_news_research_guard import news_gate
from trade_lifecycle_journal import write_event

def _snapshot(bars):
    closes=[float(b["close"]) for b in bars]
    volatility=atr(bars)
    if volatility is None or volatility<=0 or len(bars)<205:
        raise ValueError("At least 205 completed bars with valid ATR required")
    current=[ema(closes,p) for p in (20,50,200)]
    previous=[ema(closes[:-1],p) for p in (20,50,200)]
    geometry=ema_geometry(closes[-1],*current,volatility,*previous)
    return {
        "price_close":closes[-1],
        "atr14":volatility,
        "ema_geometry":vars(geometry),
        "candle_patterns":list(latest_pattern_features(bars[-5:],lookback=3)),
        "last_5_bars":[{k:float(bar[k]) for k in ("open","high","low","close")} for bar in bars[-5:]],
    }

def evaluate_market(*, symbol, observed_at_utc, bars, events,
                    calendar_updated_utc, prior_profile=None,
                    opening_range=None, journal_path=None):
    """Evaluate one completed-bar snapshot; return auditable decision records.

    This function intentionally does not send orders. The journal is optional.
    No actual news values are consumed, only scheduled high-impact event times.
    """
    if observed_at_utc.tzinfo is None:
        raise ValueError("Aware timestamp required")
    snapshot=_snapshot(bars)
    allowed,reason,event_ids=news_gate(symbol,observed_at_utc,events,calendar_updated_utc)
    candidates=scan(bars,prior_profile=prior_profile,opening_range=opening_range)
    decisions=[]
    for candidate in candidates:
        decision={
            "trade_id":str(uuid4()),"symbol":symbol,
            "strategy":candidate.strategy,"side":candidate.side,
            "entry":candidate.entry,"stop":candidate.stop,
            "target":candidate.target,"signal_reason":candidate.reason,
            "status":"candidate" if allowed else "rejected",
            "gate_reason":reason,"related_news_events":list(event_ids),
            "snapshot":snapshot,
        }
        decisions.append(decision)
        if journal_path is not None:
            write_event(journal_path,trade_id=decision["trade_id"],
                        symbol=symbol,strategy=candidate.strategy,
                        phase="signal" if allowed else "rejected",
                        observed_at_utc=observed_at_utc,values=decision)
    return {"symbol":symbol,
            "observed_at_utc":observed_at_utc.astimezone(timezone.utc).isoformat(),
            "news_allowed":allowed,"news_reason":reason,
            "snapshot":snapshot,"decisions":decisions}
