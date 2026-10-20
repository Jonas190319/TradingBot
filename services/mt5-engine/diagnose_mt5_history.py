"""Read-only MT5 M5 history diagnostics; no orders, writes or uploads."""
import argparse
from datetime import datetime, timedelta, timezone

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--markets", nargs="+", default=["XAUUSD", "NAS100"])
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--chunk-days", type=int, default=30)
    args = p.parse_args()
    if args.days < 1 or args.chunk_days < 1:
        p.error("days and chunk-days must be positive")
    import MetaTrader5 as mt5
    from main import SYMBOL_ALIASES
    if not mt5.initialize():
        raise SystemExit(f"MT5 initialization failed: {mt5.last_error()}")
    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError("Verified demo account required")
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=args.days)
        terminal = mt5.terminal_info()
        print("MT5 history diagnostic; orders=0 uploads=0")
        print(f"utc_start={start.isoformat()} utc_end={end.isoformat()} "
              f"terminal_maxbars={getattr(terminal, 'maxbars', 'unknown')}", flush=True)
        for symbol in args.markets:
            aliases = SYMBOL_ALIASES.get(symbol, [symbol])
            broker = next((s for s in aliases if mt5.symbol_info(s) is not None), None)
            if broker is None:
                print(f"{symbol} unavailable aliases={aliases}", flush=True)
                continue
            print(f"{symbol} broker={broker}", flush=True)
            whole = mt5.copy_rates_range(broker, mt5.TIMEFRAME_M5, start, end)
            print(f"  full_range_count={len(whole) if whole is not None else 'None'} "
                  f"last_error={mt5.last_error()}", flush=True)
            if whole is not None and len(whole):
                print(f"  full_first={datetime.fromtimestamp(int(whole[0]['time']),timezone.utc).isoformat()} "
                      f"full_last={datetime.fromtimestamp(int(whole[-1]['time']),timezone.utc).isoformat()}", flush=True)
            cursor = start
            unique_times = set()
            chunk_num = 0
            while cursor < end:
                nxt = min(cursor + timedelta(days=args.chunk_days), end)
                chunk = mt5.copy_rates_range(broker, mt5.TIMEFRAME_M5, cursor, nxt)
                count = len(chunk) if chunk is not None else None
                if chunk is not None:
                    unique_times.update(int(r["time"]) for r in chunk)
                print(f"  chunk={chunk_num} from={cursor.date()} to={nxt.date()} "
                      f"count={count} error={mt5.last_error()}", flush=True)
                cursor = nxt
                chunk_num += 1
            print(f"  unique_chunk_bars={len(unique_times)}", flush=True)
        print("Research only; no orders or uploads")
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    main()
