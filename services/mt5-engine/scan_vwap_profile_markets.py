"""Standalone read-only multi-market VWAP / prior-day volume profile scan.

No order API, no writes to Supabase, no changes to the running SHADOW bridge.
Only completed M5 bars. Uses UTC-day boundaries as an explicit research convention.
"""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

from vwap_volume_profile import Bar, detect_signals, volume_profile


def scan_symbol(mt5, logical, broker, now, bars_count=900):
    info = mt5.symbol_info(broker)
    if info is None:
        return {"symbol": logical, "status": "missing_symbol"}
    tick_size = float(getattr(info, "trade_tick_size", 0) or getattr(info, "point", 0) or 0)
    if tick_size <= 0:
        return {"symbol": logical, "status": "missing_tick_size"}
    rates = mt5.copy_rates_from_pos(broker, mt5.TIMEFRAME_M5, 1, bars_count)
    if rates is None or len(rates) < 30:
        return {"symbol": logical, "status": "insufficient_history"}
    sessions = {}
    latest_closed = None
    for rate in rates:
        ts = datetime.fromtimestamp(int(rate["time"]), timezone.utc)
        # Reject forming/future bars; MT5 copy_rates_from_pos(1) should already exclude current bar.
        if ts + timedelta(minutes=5) > now:
            continue
        latest_closed = ts if latest_closed is None or ts > latest_closed else latest_closed
        day = ts.date()
        sessions.setdefault(day, []).append(Bar(float(rate["high"]), float(rate["low"]),
                                                   float(rate["close"]), float(rate["tick_volume"])))
    # Do not emit weekend/stale signals from the last historical Friday bar.
    if latest_closed is None or now - (latest_closed + timedelta(minutes=5)) > timedelta(minutes=20):
        return {"symbol": logical, "status": "market_closed_or_stale",
                "last_closed_utc": latest_closed.isoformat() if latest_closed else None}
    if len(sessions) < 2:
        return {"symbol": logical, "status": "missing_prior_day"}
    today = max(sessions)
    previous_days = sorted(d for d in sessions if d < today)
    previous = previous_days[-1]
    # A short prior-day fragment can yield misleading levels: fail closed.
    if len(sessions[previous]) < 100 or len(sessions[today]) < 2:
        return {"symbol": logical, "status": "incomplete_sessions"}
    try:
        profile = volume_profile(sessions[previous], tick_size)
        tolerance = max(tick_size * 2, (max(b.high for b in sessions[today][-14:]) -
                                      min(b.low for b in sessions[today][-14:])) / 14 * 0.1)
        signals = detect_signals(sessions[today], profile, tolerance)
    except ValueError as exc:
        return {"symbol": logical, "status": "invalid_data", "reason": str(exc)}
    return {"symbol": logical, "status": "ok", "prior_day": str(previous),
            "today": str(today), "bars_today": len(sessions[today]), "bars_prior": len(sessions[previous]), "last_closed_utc": latest_closed.isoformat(),
            "vah": profile.vah, "poc": profile.poc, "val": profile.val,
            "signals": [{"strategy": s.strategy, "side": s.side, "entry": s.entry,
                         "stop": s.stop, "target": s.target} for s in signals]}


def main():
    parser = argparse.ArgumentParser(description="Read-only multi-market VWAP/profile scan; orders=0")
    parser.add_argument("--bars", type=int, default=900)
    args = parser.parse_args()
    if not 100 <= args.bars <= 3000:
        parser.error("--bars must be 100..3000")
    # Import aliases from existing bridge but do not initialize its runtime.
    from main import SYMBOL_ALIASES
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise SystemExit("MT5 connection unavailable")
    try:
        now = datetime.now(timezone.utc)
        account = mt5.account_info()
        if account is None or getattr(account, "trade_mode", None) != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError("Refusing scan: connected account is not verified demo")
        print(f"Read-only multi-market scan; account ending {str(account.login)[-4:]}; orders=0")
        for logical, aliases in SYMBOL_ALIASES.items():
            broker = next((name for name in aliases if mt5.symbol_info(name) is not None), None)
            if broker is None:
                print(f"{logical}: unavailable")
                continue
            try:
                result = scan_symbol(mt5, logical, broker, now, args.bars)
                if result["status"] == "ok":
                    print(f"{logical} ({broker}): prior={result['prior_day']} prior_bars={result['bars_prior']} today_bars={result['bars_today']} VAL={result['val']} POC={result['poc']} VAH={result['vah']} signals={result['signals']}")
                else:
                    print(f"{logical} ({broker}): {result['status']}" + (f" last_closed_utc={result['last_closed_utc']}" if result.get("last_closed_utc") else ""))
            except Exception as exc:
                print(f"{logical}: scan error {type(exc).__name__}")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
