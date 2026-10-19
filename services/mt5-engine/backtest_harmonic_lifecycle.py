"""Read-only comparative M5 harmonic lifecycle backtest; never places orders.

Patterns discovered causally on completed bars. Each horizon has an independent
tracker; next-bar-open fills and fixed stop/2R target use an OHLC cost proxy.
No uploads, order API, optimization, or live bot changes.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from harmonic_features import confirmed_pivots
from harmonic_tracker import HarmonicTracker, pattern_id
from market_features import bars_from_rates
from research_strategy_registry import MARKETS
from sequential_research_execution import simulate_signals
from services.decision_engine.harmonic_patterns import detect_shark, detect_xabcd


HORIZONS = (48, 96, 144, 288)


def evaluate(rows, symbol, tick_size, cost_ticks=2.0, max_hold=48, cost_model="legacy"):
    """Detect across observed trading bars; never fill across market closures."""
    rows = sorted(rows, key=lambda r: int(r["time"]))
    times = [int(r["time"]) for r in rows]
    if len(set(times)) != len(times) or any(b-a < 300 for a,b in zip(times,times[1:])):
        raise ValueError("Duplicate or invalid M5 timestamps")
    totals = {h: Counter() for h in HORIZONS}
    outcomes = {h: [] for h in HORIZONS}
    by_pattern = {h: defaultdict(list) for h in HORIZONS}
    # Patterns span observed trading bars, including overnight/weekend closures.
    # The simulator never fills across a closure and models gap-through-stop.
    signals = {h: [] for h in HORIZONS}
    labels = {h: {} for h in HORIZONS}
    trackers = {h: HarmonicTracker(max_age_bars=h) for h in HORIZONS}
    for i in range(300, len(rows) - 1):
        if i < 60:
            continue
        now = datetime.fromtimestamp(int(rows[i]["time"]) + 300, timezone.utc)
        bars = bars_from_rates(rows[max(0, i - 599):i + 1], now, "utc")
        tr = [max(b.high-b.low, abs(b.high-a.close), abs(b.low-a.close))
              for a, b in zip(bars[-15:-1], bars[-14:])]
        atr = sum(tr) / len(tr)
        if atr <= 0:
            continue
        pivots = confirmed_pivots(bars)
        detections = []
        if len(pivots) >= 5:
            last = pivots[-5:]
            if len(bars) - 1 - last[-1][0] <= 8:
                matches = detect_xabcd([p for _, p in last]) + detect_shark([p for _, p in last])
                detections = [(symbol, m, [p for _, p in last]) for m in matches]
        for h, tracker in trackers.items():
            # Capture state before update: signal removes it from active.
            previous = dict(tracker.active)
            events = tracker.update(i, bars[-1], atr, detections)
            for event, key, pattern in events:
                totals[h][event] += 1
                if event != "signal":
                    continue
                state = previous.get(key)
                if state is None:
                    # A signal on discovery is also valid: find its D pivot.
                    found = next(((m, ps) for sym, m, ps in detections
                                  if pattern_id(sym, m, ps) == key), None)
                    if found is None:
                        totals[h]["missing_state"] += 1
                        continue
                    match, pattern_pivots = found
                    d_price = pattern_pivots[-1].price
                    side = match.direction
                else:
                    d_price, side = state.d_price, state.direction
                reference_atr = state.reference_atr if state is not None else atr
                stop = d_price + (-1 if side == "long" else 1)*1.5*reference_atr
                signal_id = f"{h}:{key}:{i}"
                signals[h].append({"bar_index": i, "side": side,
                                   "stop": stop, "target_rr": 2.0,
                                   "signal_id": signal_id})
                labels[h][signal_id] = pattern
    for h in HORIZONS:
        result = simulate_signals(rows, signals[h], cost_ticks=cost_ticks,
                                  tick_size=tick_size, max_hold=max_hold, allow_gaps=True,
                                  cost_model=cost_model)
        outcomes[h].extend(result)
        for item in result:
            if item["outcome"] == "unresolved":
                reason = "segment_end" if item["exit_index"] >= len(rows)-1 else "max_hold"
                totals[h]["unresolved_" + reason] += 1
        for item in result:
            by_pattern[h][labels[h][item["signal_id"]]].append(item)
        totals[h]["candidate_signals"] += len(signals[h])
    return totals, outcomes, by_pattern


def main():
    parser = argparse.ArgumentParser(description="Read-only harmonic lifecycle horizon comparison")
    parser.add_argument("--history-days", type=int, choices=(30, 90, 180, 365), default=180)
    parser.add_argument("--markets", nargs="+", choices=MARKETS, default=["EURUSD", "GBPUSD"])
    parser.add_argument("--cost-ticks", type=float, default=2)
    parser.add_argument("--cost-grid", type=float, nargs="+", default=None,
                        help="Fixed-target costs on one downloaded M5 snapshot")
    parser.add_argument("--max-hold", type=int, default=48)
    parser.add_argument("--test-fraction", type=float, default=0.30,
                        help="Chronological holdout fraction; no model tuning performed")
    args = parser.parse_args()
    if args.cost_ticks < 0 or (args.cost_grid is not None and any(not 0 <= c < float("inf") for c in args.cost_grid)) or args.max_hold < 1 or not 0 < args.test_fraction < 1:
        parser.error("Invalid execution assumptions")
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
        print("Harmonic lifecycle backtest; orders=0; uploads=0", flush=True)
        for symbol in args.markets:
            broker = next((s for s in SYMBOL_ALIASES[symbol]
                           if mt5.symbol_info(s) is not None), None)
            if broker is None:
                print(symbol, "unavailable", flush=True)
                continue
            info = mt5.symbol_info(broker)
            rates = mt5.copy_rates_range(broker, mt5.TIMEFRAME_M5, start, end)
            if rates is None or len(rates) < 350:
                print(symbol, "insufficient history", flush=True)
                continue
            rows = [r for r in rates if int(r["time"]) + 300 <= end.timestamp()]
            print(symbol, "bars", len(rows), flush=True)
            if args.cost_grid is not None:
                print(f"  fixed_data_bars={len(rows)} point={float(info.point)} "
                      f"trade_tick_size={float(info.trade_tick_size)} "
                      f"snapshot_spread_points={int(info.spread)} "
                      "costs_are_assumptions_not_historical_spreads", flush=True)
                cutoff_grid = int(rows[int(len(rows)*(1-args.test_fraction))]["time"])
                for cost in args.cost_grid:
                    grid_totals, grid_outcomes, _ = evaluate(
                        rows, symbol, float(info.point), cost_ticks=cost,
                        max_hold=args.max_hold, cost_model="fixed_rr")
                    for h in HORIZONS:
                        for period, subset in (
                            ("train", [x for x in grid_outcomes[h] if int(rows[x["bar_index"]]["time"]) < cutoff_grid]),
                            ("holdout", [x for x in grid_outcomes[h] if int(rows[x["bar_index"]]["time"]) >= cutoff_grid]),
                        ):
                            resolved = [x["r"] for x in subset if x["r"] is not None]
                            marks = [x["mark_r"] for x in subset if x.get("mark_r") is not None]
                            values = resolved + marks
                            print(f"    cost_points={cost:g} horizon={h} period={period} "
                                  f"candidates={grid_totals[h]['candidate_signals']} "
                                  f"resolved={len(resolved)} wins={sum(x>0 for x in resolved)} "
                                  f"mean_R={sum(resolved)/len(resolved) if resolved else 'n/a'} "
                                  f"unresolved={len(marks)} "
                                  f"marked_mean_R={sum(values)/len(values) if values else 'n/a'}",
                                  flush=True)
                continue
            totals, outcomes, by_pattern = evaluate(rows, symbol, float(info.point),
                                        cost_ticks=args.cost_ticks, max_hold=args.max_hold)
            cutoff = rows[int(len(rows)*(1-args.test_fraction))]["time"]
            print(f"  holdout_start_utc={datetime.fromtimestamp(int(cutoff), timezone.utc).isoformat()} "
                  f"train_fraction={1-args.test_fraction:.2f} test_fraction={args.test_fraction:.2f}",
                  flush=True)
            for h in HORIZONS:
                results = outcomes[h]
                resolved = [r["r"] for r in results if r["r"] is not None]
                wins = sum(r > 0 for r in resolved)
                avg = sum(resolved)/len(resolved) if resolved else None
                print(f"  horizon={h} candidates={totals[h]['candidate_signals']} "
                      f"fills={len(results)} resolved={len(resolved)} "
                      f"wins={wins} mean_R={avg if avg is not None else 'n/a'} "
                      f"ambiguous={sum(r['outcome']=='ambiguous' for r in results)} "
                      f"unresolved={sum(r['outcome']=='unresolved' for r in results)} "
                      f"invalid_fill={sum(r['outcome']=='invalid_at_fill' for r in results)} "
                      f"no_fill_gap={sum(r['outcome']=='no_fill_gap' for r in results)} "
                      f"unresolved_max_hold={totals[h]['unresolved_max_hold']} "
                      f"unresolved_segment_end={totals[h]['unresolved_segment_end']} "
                      f"expired={totals[h]['expired']} invalidated={totals[h]['invalidated']}",
                      flush=True)
            for h in HORIZONS:
                for label, subset in (
                    ("train", [x for x in outcomes[h] if rows[x["bar_index"]]["time"] < cutoff]),
                    ("holdout", [x for x in outcomes[h] if rows[x["bar_index"]]["time"] >= cutoff]),
                ):
                    resolved = [x["r"] for x in subset if x["r"] is not None]
                    marks = [x.get("mark_r") for x in subset if x["outcome"] == "unresolved"]
                    marks = [v for v in marks if v is not None]
                    all_marked = resolved + marks
                    print(f"    horizon={h} period={label} resolved={len(resolved)} "
                          f"wins={sum(x > 0 for x in resolved)} "
                          f"resolved_mean_R={sum(resolved)/len(resolved) if resolved else 'n/a'} "
                          f"unresolved_marked={len(marks)} "
                          f"marked_mean_R={sum(all_marked)/len(all_marked) if all_marked else 'n/a'} "
                          f"ambiguous={sum(x['outcome']=='ambiguous' for x in subset)}",
                          flush=True)
            # Detailed per-pattern chronology; report every horizon without
            # changing pattern ratios or selecting winners.
            for h in HORIZONS:
                for pattern, pattern_results in sorted(by_pattern[h].items()):
                    for period, subset in (
                        ("train", [x for x in pattern_results
                                   if rows[x["bar_index"]]["time"] < cutoff]),
                        ("holdout", [x for x in pattern_results
                                     if rows[x["bar_index"]]["time"] >= cutoff]),
                    ):
                        if not subset:
                            continue
                        resolved = [x["r"] for x in subset if x["r"] is not None]
                        marks = [x["mark_r"] for x in subset if x.get("mark_r") is not None]
                        combined = resolved + marks
                        print(f"    horizon={h} pattern={pattern} period={period} "
                              f"fills={len(subset)} resolved={len(resolved)} "
                              f"wins={sum(x>0 for x in resolved)} "
                              f"mean_R={sum(resolved)/len(resolved) if resolved else 'n/a'} "
                              f"marked_mean_R={sum(combined)/len(combined) if combined else 'n/a'} "
                              f"ambiguous={sum(x['outcome']=='ambiguous' for x in subset)}",
                              flush=True)
            for h in HORIZONS:
                for pattern, pattern_results in sorted(by_pattern[h].items()):
                    resolved = [x["r"] for x in pattern_results if x["r"] is not None]
                    avg = sum(resolved)/len(resolved) if resolved else None
                    print(f"    horizon={h} pattern={pattern} fills={len(pattern_results)} "
                          f"resolved={len(resolved)} mean_R={avg if avg is not None else 'n/a'}",
                          flush=True)
        print("Research only; no orders or uploads", flush=True)
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
