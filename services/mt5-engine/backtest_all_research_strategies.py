"""Historical, read-only M5 research across all 16 strategies and eight markets.

Research assumptions: completed candles only, signal at candle close, hypothetical
fill at that close, future OHLC used only for outcome. No spread/slippage/fees,
broker fills, commissions, portfolio overlap or walk-forward validation.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scan_all_research_strategies import evaluate_existing
from research_outcomes import evaluate_outcome, summarize_outcomes
from research_strategy_registry import MARKETS, STRATEGIES
from vwap_volume_profile import Bar, detect_signals, volume_profile


def research_market(logical, rates, tick_size, lookahead=48, warmup=300, step=5, cost_ticks=0):
    """Pure historical research. Rates must be chronological, completed M5 candles."""
    if not 1 <= lookahead <= 288 or not 60 <= warmup or not 1 <= step or cost_ticks < 0:
        raise ValueError("Invalid research window")
    rows = sorted(rates, key=lambda r: int(r["time"]))
    times = [int(r["time"]) for r in rows]
    if len(times) != len(set(times)):
        raise ValueError("Duplicate historical M5 timestamps")
    if not tick_size or tick_size <= 0:
        raise ValueError("Invalid tick size")
    by_day = defaultdict(list)
    for r in rows:
        ts = datetime.fromtimestamp(int(r["time"]), timezone.utc)
        by_day[ts.date()].append(Bar(float(r["high"]), float(r["low"]),
                                         float(r["close"]), float(r["tick_volume"])))
    dates = sorted(by_day)
    profiles = {}
    for day in dates[1:]:
        prior = dates[dates.index(day)-1]
        minimum = 230 if logical == "GER40" else 270 if logical in ("XAUUSD", "NAS100", "US500", "US30") else 280
        if len(by_day[prior]) >= minimum:
            try:
                profiles[day] = volume_profile(by_day[prior], tick_size)
            except ValueError:
                pass
    outcomes = defaultdict(list)
    observations = defaultdict(int)
    skipped_future_gaps = 0
    for i in range(warmup, len(rows)-lookahead, step):
        ts = datetime.fromtimestamp(times[i], timezone.utc)
        # Do not evaluate across a stale session boundary; latest 60 bars must be contiguous.
        if any(times[j+1]-times[j] != 300 for j in range(i-59, i)):
            continue
        # Skip windows with missing bars or session/weekend gaps in the outcome period.
        if any(times[j+1] - times[j] != 300 for j in range(i, i+lookahead)):
            skipped_future_gaps += 1
            continue
        now = ts + timedelta(minutes=5)
        past = rows[max(0, i-599):i+1]
        # Research quote proxy: use the signal bar close, not a present-day quote.
        price = float(rows[i]["close"])
        try:
            existing, _ = evaluate_existing(logical, past, now, price, price)
        except (ValueError, RuntimeError, KeyError, ZeroDivisionError):
            continue
        candidates = [(name, c) for name, c in existing.items() if c is not None]
        for name in existing:
            observations[name] += 1
        profile = profiles.get(ts.date())
        if profile is not None:
            today = [Bar(float(r["high"]), float(r["low"]), float(r["close"]),
                         float(r["tick_volume"])) for r in past
                     if datetime.fromtimestamp(int(r["time"]), timezone.utc).date() == ts.date()]
            if len(today) >= 2:
                tolerance = max(tick_size*2,
                                (max(b.high for b in today[-14:])-min(b.low for b in today[-14:]))/14*0.1)
                try:
                    signals = detect_signals(today, profile, tolerance)
                    candidates += [(s.strategy, {"side": s.side, "entry": s.entry,
                                                   "stop": s.stop, "target": s.target}) for s in signals]
                    for name in STRATEGIES[13:]:
                        observations[name] += 1
                except ValueError:
                    pass
        future = rows[i+1:i+1+lookahead]
        for name, c in candidates:
            # Some strategists may return a quote-mid entry; this is only a proxy.
            try:
                outcome = evaluate_outcome(c["side"], c["entry"], c["stop"],
                                           c["target"], future, lookahead)
                if outcome["r"] is not None:
                    risk = abs(float(c["entry"]) - float(c["stop"]))
                    outcome = dict(outcome, r=outcome["r"] - cost_ticks*tick_size/risk)
                outcomes[name].append(outcome)
            except (ValueError, TypeError, KeyError):
                continue
    report = {name: {"observations": observations[name],
                   **summarize_outcomes(outcomes[name])} for name in STRATEGIES}
    return report, {"first_utc": datetime.fromtimestamp(times[0], timezone.utc).isoformat(),
                    "last_utc": datetime.fromtimestamp(times[-1], timezone.utc).isoformat(),
                    "skipped_future_gaps": skipped_future_gaps}


def main():
    p = argparse.ArgumentParser(description="Historical research only; no orders or uploads")
    p.add_argument("--bars", type=int, default=1600)
    p.add_argument("--lookahead", type=int, default=48)
    p.add_argument("--step", type=int, default=5)
    p.add_argument("--cost-ticks", type=float, default=0,
                   help="Assumed round-trip cost in tick-size units; not measured broker spread")
    args = p.parse_args()
    if not 1000 <= args.bars <= 5000 or not 1 <= args.lookahead <= 288 or not 1 <= args.step <= 100 or not 0 <= args.cost_ticks <= 1000:
        p.error("Invalid bars/lookahead/step")
    import MetaTrader5 as mt5
    from main import SYMBOL_ALIASES
    if not mt5.initialize():
        raise SystemExit("MT5 unavailable")
    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError("Verified demo account required")
        print(f"Historical research: 16 strategies x 8 markets; bars={args.bars}; step={args.step}; orders=0; uploads=0")
        for logical in MARKETS:
            broker = next((x for x in SYMBOL_ALIASES[logical] if mt5.symbol_info(x) is not None), None)
            if broker is None:
                print(f"{logical}: unavailable")
                continue
            rates = mt5.copy_rates_from_pos(broker, mt5.TIMEFRAME_M5, 1, args.bars)
            if rates is None or len(rates) < 1000:
                print(f"{logical}: insufficient_history")
                continue
            info = mt5.symbol_info(broker)
            tick_size = float(getattr(info, "trade_tick_size", 0) or getattr(info, "point", 0) or 0)
            try:
                result, quality = research_market(logical, rates, tick_size, args.lookahead,
                                                  step=args.step, cost_ticks=args.cost_ticks)
                print(f"\n{logical} ({broker}): {quality}")
                for strategy, summary in result.items():
                    rate = f"{summary['win_rate']:.1%}" if summary["win_rate"] is not None else "n/a"
                    mean_r = f"{summary['mean_r']:.2f}" if summary["mean_r"] is not None else "n/a"
                    print(f"  {strategy}: scans={summary['observations']} signals={summary['signals']} "
                          f"resolved={summary['resolved']} ambiguous={summary['ambiguous']} "
                          f"unresolved={summary['unresolved']} win={rate} avgR={mean_r}")
            except (ValueError, RuntimeError) as exc:
                print(f"{logical}: skipped {type(exc).__name__}: {exc}")
        print("Research only: results are not live trading performance; orders=0; uploads=0")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
