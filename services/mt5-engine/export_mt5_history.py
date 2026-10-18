"""Read-only MetaTrader 5 deal history export. No order APIs or database writes."""
import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

FIELDS = ("ticket", "order", "position_id", "time_utc", "symbol", "type",
          "entry", "reason", "volume", "price", "profit", "commission",
          "swap", "fee", "magic", "comment")


def deal_row(deal):
    """Convert an MT5 deal to a stable, account-scoped CSV row."""
    return {
        "ticket": int(deal.ticket),
        "order": int(deal.order),
        "position_id": int(deal.position_id),
        "time_utc": datetime.fromtimestamp(deal.time, timezone.utc).isoformat(),
        "symbol": str(deal.symbol),
        "type": int(deal.type),
        "entry": int(deal.entry),
        "reason": int(deal.reason),
        "volume": float(deal.volume),
        "price": float(deal.price),
        "profit": float(deal.profit),
        "commission": float(deal.commission),
        "swap": float(deal.swap),
        "fee": float(deal.fee),
        "magic": int(deal.magic),
        "comment": str(deal.comment),
    }


def collect_history(mt5, start, end):
    """Query all available deals for the selected time range; fail on MT5 errors."""
    if not start < end:
        raise ValueError("Start must be earlier than end")
    deals = mt5.history_deals_get(start, end)
    if deals is None:
        raise RuntimeError(f"MT5 history query failed: {mt5.last_error()}")
    rows = [deal_row(deal) for deal in deals]
    rows.sort(key=lambda row: (row["time_utc"], row["ticket"]))
    return rows


def main():
    parser = argparse.ArgumentParser(description="Read-only MT5 deal history export")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--output", default="mt5_deals.csv")
    args = parser.parse_args()
    if not 1 <= args.days <= 3650:
        parser.error("--days must be between 1 and 3650")
    from datetime import timedelta
    import MetaTrader5 as mt5
    # Attach to the already open terminal; do not log in or switch accounts.
    if not mt5.initialize():
        raise SystemExit(f"MT5 initialization failed: {mt5.last_error()}")
    try:
        account = mt5.account_info()
        if account is None:
            raise RuntimeError("No active MT5 account")
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=args.days)
        rows = collect_history(mt5, start, now)
        path = Path(args.output).resolve()
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite existing export: {path}")
        with path.open("x", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Exported {len(rows)} MT5 deals for account ending {str(account.login)[-4:]} to {path.name}")
        print("Read-only export completed. No orders sent and no data uploaded.")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
