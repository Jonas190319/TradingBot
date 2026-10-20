"""Offline smoke tests for the six-strategy research configuration."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import importlib.util
import sys
BASE=Path(__file__).resolve().parents[1] / "services" / "mt5-engine"
def load(name):
    spec=importlib.util.spec_from_file_location(name,BASE/(name+".py"))
    mod=importlib.util.module_from_spec(spec)
    sys.modules[name]=mod
    spec.loader.exec_module(mod)
    return mod

def test_portfolio():
    p=load("research_portfolio_15_markets")
    assert p.validate_configuration()
    assert len(p.candidate_matrix())==90

def test_ema():
    e=load("ema_geometry_features")
    v=e.ema_geometry(104,103,102,100,2,102.5,101.5,99.8)
    assert v.alignment=="bullish"
    assert v.price_ema20_atr==0.5

def test_news():
    g=load("macro_news_research_guard")
    s=load("indicator_news_tracker_schema")
    now=datetime(2026,10,20,12,tzinfo=timezone.utc)
    assert not g.news_gate("EURUSD",now,[],None)[0]
    assert g.news_gate("EURUSD",now,[],now)[0]
    e=s.EconomicEvent("cpi",now+timedelta(minutes=10),"USD","CPI","high")
    assert g.news_gate("EURUSD",now,[e],now)[1]=="high_impact_event"
    assert g.news_gate("GER40",now,[e],now)[0]

def test_scan():
    s=load("six_strategy_signal_engine")
    bars=[{"open":100+i*.01,"high":100+i*.01+.2,
           "low":100+i*.01-.2,"close":100+i*.01} for i in range(240)]
    assert s.scan(bars)==s.scan(bars)
