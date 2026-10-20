"""Integration checks: all six-strategy research pipeline modules run without MT5."""
import sys
from datetime import datetime, timezone
from pathlib import Path

ENGINE=Path(__file__).resolve().parents[1]/"services"/"mt5-engine"
sys.path.insert(0,str(ENGINE))
from research_signal_pipeline import evaluate_market
from trade_lifecycle_journal import excursions

def sample_bars():
    return [
        {"open":100+i*0.01,"high":100+i*0.01+0.20,
         "low":100+i*0.01-0.20,"close":100+i*0.01}
        for i in range(240)
    ]

def test_pipeline_news_fails_closed(tmp_path):
    path=tmp_path/"events.jsonl"
    result=evaluate_market(symbol="EURUSD",
        observed_at_utc=datetime(2026,10,20,12,tzinfo=timezone.utc),
        bars=sample_bars(),events=[],calendar_updated_utc=None,
        journal_path=path)
    assert result["news_allowed"] is False
    assert result["news_reason"]=="calendar_unavailable"
    assert result["snapshot"]["ema_geometry"]["alignment"]=="bullish"
    assert isinstance(result["snapshot"]["candle_patterns"],list)
    assert all(x["status"]=="rejected" for x in result["decisions"])

def test_pipeline_fresh_calendar():
    now=datetime(2026,10,20,12,tzinfo=timezone.utc)
    result=evaluate_market(symbol="EURUSD",observed_at_utc=now,
        bars=sample_bars(),events=[],calendar_updated_utc=now)
    assert result["news_allowed"] is True
    assert result["news_reason"]=="clear"

def test_excursions():
    mfe,mae=excursions("long",100,99,[100.4,101.2],[99.7,99.8])
    assert abs(mfe-1.2)<1e-9
    assert abs(mae-0.3)<1e-9
