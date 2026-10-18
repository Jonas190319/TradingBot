"""Conservative sequential OHLC research execution (no broker access).

Signals are generated from a completed M5 candle. Earliest hypothetical fill
is the NEXT M5 open. One open position per strategy/market. No gap bridging.
No fill orders, account sizing, portfolio allocation or live execution.
"""
from datetime import datetime, timezone
from math import isfinite


def simulate_signals(rows, signals, cost_ticks=0.0, tick_size=0.0, max_hold=48, allow_gaps=False):
    """Return sequential outcomes for candidate dicts with bar_index, side, stop, target.

    OHLC execution proxy: next bar open, with unfavorable entry slippage of
    cost_ticks*tick_size (full assumed round-trip cost). Stop/target are fixed.
    A stop+target touch on the same candle is ambiguous, never a win.
    A price gap through stop exits at the adverse open; target gap exits at
    target (no favorable price improvement). Open positions at the end are
    unresolved; overlapping signals are skipped. Signals on same candle are
    processed in input order; caller should separate each strategy/market.
    """
    if not isinstance(max_hold, int) or max_hold < 1:
        raise ValueError("Invalid max_hold")
    if not all(isfinite(float(v)) and float(v) >= 0 for v in (cost_ticks, tick_size)):
        raise ValueError("Invalid cost settings")
    times = [int(x["time"]) for x in rows]
    if any((b-a < 300 or (b-a != 300 and not allow_gaps)) for a,b in zip(times,times[1:])):
        raise ValueError("Invalid M5 timestamps or gaps not permitted")
    outcomes = []
    busy_until = -1
    for signal in sorted(signals, key=lambda s: int(s["bar_index"])):
        i = int(signal["bar_index"])
        if i <= busy_until or i < 0 or i+1 >= len(rows):
            continue
        if times[i+1] - times[i] != 300:
            # No hypothetical fill across a closed-market interval.
            outcomes.append({"outcome":"no_fill_gap", "r":None,
                             "bar_index":i, "exit_index":i,
                             **({"signal_id":signal["signal_id"]} if "signal_id" in signal else {})})
            continue
        side = signal["side"]
        stop = float(signal["stop"])
        rr = signal.get("target_rr")
        target = float(signal["target"]) if rr is None else None
        entry = float(rows[i+1]["open"])
        if side not in ("long", "short"):
            raise ValueError("Invalid side")
        if not all(isfinite(x) and x > 0 for x in (entry, stop)) or (target is not None and (not isfinite(target) or target <= 0)):
            raise ValueError("Invalid prices")
        # No favorable repricing: charge full round-trip cost to entry.
        entry += (1 if side == "long" else -1)*cost_ticks*tick_size
        if rr is not None:
            rr = float(rr)
            if not isfinite(rr) or rr <= 0:
                raise ValueError("Invalid target_rr")
            target = entry + (1 if side == "long" else -1)*rr*abs(entry-stop)
        if not ((side == "long" and stop < entry < target) or
                (side == "short" and target < entry < stop)):
            outcomes.append({"outcome":"invalid_at_fill", "r":None,
                             "bar_index":i, "exit_index":i+1,
                             **({"signal_id":signal["signal_id"]} if "signal_id" in signal else {})})
            continue
        risk = abs(entry-stop)
        result = {"outcome":"unresolved", "r":None, "bar_index":i,
                  "entry":entry, "exit_index":min(len(rows)-1,i+max_hold)}
        end = min(len(rows), i+1+max_hold)
        for j in range(i+1,end):
            bar = rows[j]
            op,hi,lo = (float(bar[k]) for k in ("open","high","low"))
            if not all(isfinite(x) and x > 0 for x in (op,hi,lo)) or not lo <= op <= hi:
                raise ValueError("Invalid OHLC")
            hit_stop = lo <= stop if side=="long" else hi >= stop
            hit_target = hi >= target if side=="long" else lo <= target
            # At a reopened market, execute adverse gap-through-stop first.
            if j > i+1 and times[j] - times[j-1] > 300 and (op <= stop if side=="long" else op >= stop):
                pnl = (op-entry) if side=="long" else (entry-op)
                result.update(outcome="stop_gap",r=pnl/risk,exit_index=j)
                break
            if hit_stop and hit_target:
                result.update(outcome="ambiguous",r=None,exit_index=j)
                break
            if hit_stop:
                # Adverse stop gaps are priced at the open if worse than stop.
                exit_price = min(op,stop) if side=="long" else max(op,stop)
                pnl = (exit_price-entry) if side=="long" else (entry-exit_price)
                result.update(outcome="stop",r=pnl/risk,exit_index=j)
                break
            if hit_target:
                pnl = (target-entry) if side=="long" else (entry-target)
                result.update(outcome="target",r=pnl/risk,exit_index=j)
                break
        if result["outcome"] == "unresolved":
            # End-of-horizon mark-to-market proxy, not an executed exit.
            last_close = float(rows[result["exit_index"]]["close"])
            if not isfinite(last_close) or last_close <= 0:
                raise ValueError("Invalid final close")
            result["mark_r"] = ((last_close-entry) if side=="long"
                                else (entry-last_close))/risk
        if "signal_id" in signal:
            result["signal_id"] = signal["signal_id"]
        outcomes.append(result)
        busy_until = result["exit_index"]
    return outcomes
