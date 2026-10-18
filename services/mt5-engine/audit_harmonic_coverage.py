"""Read-only M5 history coverage audit for harmonic backtest.

Shows exactly which bars the current contiguous-350 / warmup-300
algorithm can evaluate. Does not submit orders or upload data.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone

from research_strategy_registry import MARKETS


def coverage(rows, min_segment=350, warmup=300):
    times = sorted(int(r["time"]) for r in rows)
    if len(set(times)) != len(times):
        raise ValueError("Duplicate M5 timestamps")
    if min_segment <= warmup or warmup < 1:
        raise ValueError("Invalid coverage thresholds")
    lengths = []
    gaps = Counter()
    start = 0
    for end in range(1, len(times) + 1):
        if end < len(times) and times[end] - times[end-1] == 300:
            continue
        lengths.append(end-start)
        if end < len(times):
            gaps[times[end]-times[end-1]-300] += 1
        start = end
    eligible = [n for n in lengths if n >= min_segment]
    # The last bar of a segment cannot open a trade on a next M5 candle.
    evaluated = sum(n-warmup-1 for n in eligible)
    skipped_short = sum(n for n in lengths if n < min_segment)
    skipped_warmup = sum(warmup+1 for n in eligible)
    assert evaluated + skipped_short + skipped_warmup == len(times)
    return dict(bars=len(times), segments=len(lengths), eligible_segments=len(eligible),
                shortest=min(lengths, default=0), longest=max(lengths, default=0),
                evaluated=evaluated, skipped_short=skipped_short,
                skipped_warmup=skipped_warmup,
                coverage_pct=100*evaluated/len(times) if times else 0,
                gap_counts=gaps, segment_lengths=lengths)


def main():
    p = argparse.ArgumentParser(description="Audit M5 coverage without orders/uploads")
    p.add_argument("--history-days", type=int, choices=(30,90,180,365), default=180)
    p.add_argument("--markets", nargs="+", choices=MARKETS, default=list(MARKETS))
    args = p.parse_args()
    import MetaTrader5 as mt5
    from main import SYMBOL_ALIASES
    if not mt5.initialize():
        raise SystemExit("MT5 unavailable")
    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError("Verified demo account required")
        end = datetime.now(timezone.utc)
        start = end-timedelta(days=args.history_days)
        print("M5 coverage audit; orders=0; uploads=0", flush=True)
        for market in args.markets:
            broker = next((s for s in SYMBOL_ALIASES[market] if mt5.symbol_info(s) is not None), None)
            if broker is None:
                print(market, "unavailable", flush=True)
                continue
            rates = mt5.copy_rates_range(broker, mt5.TIMEFRAME_M5, start, end)
            if rates is None:
                print(market, "history unavailable", flush=True)
                continue
            rows = [r for r in rates if int(r["time"])+300 <= end.timestamp()]
            c = coverage(rows)
            top = sorted(c["gap_counts"].items(), key=lambda kv: -kv[1])[:4]
            print(f'{market} bars={c["bars"]} segments={c["segments"]} '
                  f'eligible={c["eligible_segments"]} evaluated={c["evaluated"]} '
                  f'coverage={c["coverage_pct"]:.1f}% skipped_short={c["skipped_short"]} '
                  f'skipped_warmup={c["skipped_warmup"]} '
                  f'min_segment={c["shortest"]} max_segment={c["longest"]} '
                  f'common_gaps_seconds={top}', flush=True)
        print("Audit complete; orders=0; uploads=0", flush=True)
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
