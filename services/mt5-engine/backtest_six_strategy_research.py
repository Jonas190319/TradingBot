"""Read-only MT5 historical signal research, 15 markets x six strategies.

No order calls. Writes local JSON/CSV only. First-pass signals and simulated
outcomes use M5 OHLC; intrabar stop/target collisions count as stop first.
News and broker execution costs are NOT modeled; do not treat as live expectancy.
"""
import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
import MetaTrader5 as mt5
from research_portfolio_15_markets import MARKETS, broker_symbol
from six_strategy_signal_engine import scan
from candlestick_pattern_tracker import latest_pattern_features
from ema_geometry_features import ema_geometry
from six_strategy_signal_engine import ema, atr

def load_bars(symbol, count):
    if not mt5.symbol_select(symbol, True):
        return []
    rates=mt5.copy_rates_from_pos(symbol,mt5.TIMEFRAME_M5,1,count)
    if rates is None:
        return []
    return [
        {"time":int(x["time"]),"open":float(x["open"]),
         "high":float(x["high"]),"low":float(x["low"]),
         "close":float(x["close"]),"tick_volume":int(x["tick_volume"])}
        for x in rates
    ]

def outcome(candidate, future):
    """Stop-first pessimistic outcome for ambiguous M5 bars."""
    entry,stop,target=candidate.entry,candidate.stop,candidate.target
    risk=abs(entry-stop)
    if risk<=0:
        return {"result":"invalid","r":None,"mfe_r":None,"mae_r":None}
    side=candidate.side
    mfe=mae=0.0
    for i,b in enumerate(future,1):
        favourable=(b["high"]-entry) if side=="long" else (entry-b["low"])
        adverse=(entry-b["low"]) if side=="long" else (b["high"]-entry)
        mfe=max(mfe,favourable/risk)
        mae=max(mae,adverse/risk)
        stop_hit=b["low"]<=stop if side=="long" else b["high"]>=stop
        target_hit=b["high"]>=target if side=="long" else b["low"]<=target
        if stop_hit:
            return {"result":"stop","r":-1.0,"mfe_r":round(mfe,4),"mae_r":round(mae,4),"bars_held":i}
        if target_hit:
            return {"result":"target","r":round(abs(target-entry)/risk,4),
                    "mfe_r":round(mfe,4),"mae_r":round(mae,4),"bars_held":i}
    return {"result":"unresolved","r":None,"mfe_r":round(mfe,4),
            "mae_r":round(mae,4),"bars_held":len(future)}

def run(symbols, bars_count, step, horizon):
    rows=[]
    for logical in symbols:
        actual=broker_symbol(logical)
        history=load_bars(actual,bars_count)
        print(f"{logical:8} -> {actual:12} {len(history):6} M5 bars",flush=True)
        if len(history)<300:
            continue
        # No profile/opening range passed: those strategies are intentionally
        # NOT tested until a causally correct session builder is integrated.
        for i in range(205,len(history)-horizon,step):
            window=history[:i+1]
            signals=scan(window)
            if not signals:
                continue
            closes=[b["close"] for b in window]
            a=atr(window)
            geom=ema_geometry(closes[-1],*(ema(closes,p) for p in (20,50,200)),
                              a,*(ema(closes[:-1],p) for p in (20,50,200)))
            patterns=latest_pattern_features(window[-5:])
            for s in signals:
                row={"market":logical,"broker_symbol":actual,"strategy":s.strategy,
                     "signal_utc":datetime.fromtimestamp(history[i]["time"],timezone.utc).isoformat(),
                     "side":s.side,"entry":s.entry,"stop":s.stop,"target":s.target,
                     "reason":s.reason,"ema_alignment":geom.alignment,
                     "price_ema20_atr":round(geom.price_ema20_atr,4),
                     "ema20_ema50_atr":round(geom.ema20_ema50_atr,4),
                     "patterns":";".join(p["pattern"] for p in patterns),
                     **outcome(s,history[i+1:i+1+horizon])}
                rows.append(row)
        print(f"  signals so far: {len(rows)}",flush=True)
    return rows

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--bars",type=int,default=5000)
    parser.add_argument("--step",type=int,default=5)
    parser.add_argument("--horizon",type=int,default=48)
    parser.add_argument("--out",default="research_outputs/six_strategy_signals.csv")
    args=parser.parse_args()
    if args.bars<300 or args.step<1 or args.horizon<1:
        parser.error("bars>=300, step>=1, horizon>=1 required")
    if not mt5.initialize():
        raise SystemExit(f"MT5 initialization failed: {mt5.last_error()}")
    try:
        account=mt5.account_info()
        if account is None or account.trade_mode!=mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise SystemExit("Demo account required; no data collected.")
        rows=run(MARKETS,args.bars,args.step,args.horizon)
    finally:
        mt5.shutdown()
    dest=Path(args.out)
    dest.parent.mkdir(parents=True,exist_ok=True)
    fields=["market","broker_symbol","strategy","signal_utc","side","entry",
            "stop","target","reason","ema_alignment","price_ema20_atr",
            "ema20_ema50_atr","patterns","result","r","mfe_r","mae_r","bars_held"]
    with dest.open("w",newline="",encoding="utf-8-sig") as f:
        writer=csv.DictWriter(f,fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} candidate signals to {dest}")
    print("WARNING: M5 OHLC-only, no spreads/news; volume profile and ORB not evaluated.")
if __name__=="__main__":
    main()
