"""Explicit, read-only MT5 history -> private Supabase journal importer.

No MT5 order API. No upload unless --commit is supplied.
Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in local environment/.env.
"""
import argparse
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request
import json

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_mt5_history import collect_history


def load_env(path):
    """Load local .env without overriding existing environment variables."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def to_record(row, account_server, account_login):
    return {
        "account_server": account_server,
        "account_login": account_login,
        "ticket": row["ticket"],
        "order_ticket": row["order"],
        "position_id": row["position_id"],
        "time_utc": row["time_utc"],
        "symbol": row["symbol"],
        "deal_type": row["type"],
        "deal_entry": row["entry"],
        "deal_reason": row["reason"],
        "volume": row["volume"],
        "price": row["price"],
        "profit": row["profit"],
        "commission": row["commission"],
        "swap": row["swap"],
        "fee": row["fee"],
        "magic": row["magic"],
        "comment": row["comment"],
    }


def upsert_batch(base_url, secret, records):
    url = base_url.rstrip("/") + "/rest/v1/mt5_history_deals?on_conflict=account_server,account_login,ticket"
    request = urllib.request.Request(
        url,
        data=json.dumps(records, allow_nan=False).encode("utf-8"),
        method="POST",
        headers={
            "apikey": secret,
            "Authorization": "Bearer " + secret,
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status not in (200, 201, 204):
            raise RuntimeError("Unexpected Supabase HTTP status: " + str(response.status))


def main():
    parser = argparse.ArgumentParser(description="Read-only MT5 -> Supabase deal journal")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--commit", action="store_true", help="Actually upload; default is dry-run")
    parser.add_argument("--env-file", type=Path, help="Explicit local .env path")
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.days <= 3650 or not 1 <= args.batch_size <= 500:
        parser.error("Invalid days or batch size")
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise SystemExit("MT5 connection failed; check open terminal")
    try:
        account = mt5.account_info()
        if account is None or not account.login or not account.server:
            raise RuntimeError("MT5 account identification unavailable")
        env_path = args.env_file if args.env_file else Path(__file__).resolve().parents[2] / ".env"
        if not env_path.is_file():
            raise RuntimeError(f"Local configuration file not found: {env_path}")
        load_env(env_path)
        expected_login = os.environ.get("MT5_LOGIN", "").strip()
        expected_server = os.environ.get("MT5_SERVER", "").strip()
        if not expected_login or not expected_server:
            raise RuntimeError("Set MT5_LOGIN and MT5_SERVER in local .env before importing")
        if str(account.login) != expected_login or str(account.server) != expected_server:
            raise RuntimeError("Connected MT5 account does not match local .env; refusing import")
        end = datetime.now(timezone.utc)
        rows = collect_history(mt5, end - timedelta(days=args.days), end)
        records = [to_record(row, str(account.server), int(account.login)) for row in rows]
        tickets = [r["ticket"] for r in records]
        if len(tickets) != len(set(tickets)):
            raise RuntimeError("Duplicate deal tickets in MT5 response")
        print(f"Account ending {str(account.login)[-4:]}: {len(records)} deals in {args.days} days")
        print("Gross profit:", round(sum(r["profit"] for r in records), 2))
        print("Net of deal costs:", round(sum(r["profit"] + r["commission"] + r["swap"] + r["fee"] for r in records), 2))
        if not args.commit:
            print("DRY RUN: no data uploaded. Add --commit after creating the private Supabase table.")
            return
        base_url = os.environ.get("SUPABASE_URL", "").strip()
        secret = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not base_url.startswith("https://") or not secret:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required in local .env")
        for i in range(0, len(records), args.batch_size):
            upsert_batch(base_url, secret, records[i:i + args.batch_size])
        print(f"Uploaded/upserted {len(records)} deal records; no broker orders sent.")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
