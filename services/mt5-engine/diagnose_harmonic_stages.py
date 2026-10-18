"""Read-only harmonic stage diagnostics on completed M5 history.

No trade execution, uploads, or changes to existing strategy backtests.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from harmonic_features import confirmed_pivots
from market_features import bars_from_rates
from services.decision_engine.harmonic_patterns import (
    classify_completion_zone, detect_shark, detect_xabcd,
)
from research_strategy_registry import MARKETS


def diagnose(rates, step=1, warmup=300):
    """Evaluate only fully closed, contiguous windows; report observed stages."""
    rows = sorted(rates, key=lambda r: int(r["time"]))
    times = [int(row["time"]) for row in rows]
    if len(set(times)) != len(times):
        raise ValueError("Duplicate M5 timestamps")
    counts = Counter()
    unique = set()
    for i in range(warmup, len(rows), step):
        if any(times[j + 1] - times[j] != 300 for j in range(i - 59, i)):
            counts["skipped_recent_gap"] += 1
            continue
        now = datetime.fromtimestamp(times[i] + 300, timezone.utc)
        bars = bars_from_rates(rows[max(0, i - 599):i + 1], now, "utc")
        counts["evaluated"] += 1
        pivots = confirmed_pivots(bars)
        if len(pivots) < 5:
            continue
        counts["five_pivots"] += 1
        last = pivots[-5:]
        d_index, d = last[-1]
        if len(bars) - 1 - d_index > 8:
            continue
        counts["fresh_d"] += 1
        matches = detect_xabcd([p for _, p in last]) + detect_shark([p for _, p in last])
        if not matches:
            continue
        counts["ratio_windows"] += 1
        true_ranges = [
            max(cur.high - cur.low, abs(cur.high - prev.close),
                abs(cur.low - prev.close))
            for prev, cur in zip(bars[-15:-1], bars[-14:])
        ]
        atr = sum(true_ranges) / len(true_ranges)
        if atr <= 0:
            continue
        for match in matches:
            key = (match.pattern, tuple(p.timestamp for _, p in last))
            counts["ratio_matches"] += 1
            unique.add(key)
            counts["pattern_" + match.pattern] += 1
            zone = classify_completion_zone(
                match.direction, d.price, bars[-1].close, atr
            )
            status = zone["status"]
            counts["zone_" + status] += 1
            if status != "entry_zone":
                continue
            confirmed = (
                bars[-1].close > bars[-1].open if match.direction == "long"
                else bars[-1].close < bars[-1].open
            )
            if confirmed:
                counts["zone_and_candle_confirmed"] += 1
            else:
                counts["zone_without_candle_confirmation"] += 1
    counts["unique_ratio_patterns"] = len(unique)
    return dict(sorted(counts.items()))


def main():
    parser = argparse.ArgumentParser(description="Read-only harmonic M5 diagnostics")
    parser.add_argument("--history-days", type=int, choices=(30, 90, 180, 365), default=180)
    parser.add_argument("--step", type=int, choices=(1, 5, 20), default=1)
    parser.add_argument("--markets", nargs="+", choices=MARKETS, default=["EURUSD", "GBPUSD"])
    args = parser.parse_args()
    import MetaTrader5 as mt5
    from main import SYMBOL_ALIASES
    if not mt5.initialize():
        raise SystemExit("MT5 unavailable")
    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError("Verified demo account required")
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=args.history_days)
        print("Harmonic stage diagnostics; orders=0; uploads=0")
        for logical in args.markets:
            broker = next((s for s in SYMBOL_ALIASES[logical]
                           if mt5.symbol_info(s) is not None), None)
            if broker is None:
                print(f"{logical}: unavailable")
                continue
            rates = mt5.copy_rates_range(broker, mt5.TIMEFRAME_M5, start, end)
            if rates is None or len(rates) < 1000:
                print(f"{logical}: insufficient history")
                continue
            # Exclude current forming bar and future timestamps.
            completed = [r for r in rates
                         if datetime.fromtimestamp(int(r["time"]) + 300, timezone.utc) <= end]
            print(f"{logical}: bars={len(completed)} step={args.step}")
            print(diagnose(completed, step=args.step))
        print("Research only; no orders or uploads")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
