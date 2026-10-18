"""Opt-in Supabase upload of unified 16-strategy research candidates.

DRY RUN by default. DEMO account only. No order API. Does not touch the Shadow bot.
"""
import argparse
import json
import os
from pathlib import Path
import urllib.request

from import_mt5_history import load_env
from scan_all_research_strategies import run


def submit_records(records, url, key):
    if not url.startswith("https://") or not key:
        raise RuntimeError("Supabase configuration missing")
    if not records:
        return
    req = urllib.request.Request(
        url.rstrip("/") + "/rest/v1/mt5_strategy_research_journal?on_conflict=signal_id",
        data=json.dumps(records, allow_nan=False).encode("utf-8"),
        method="POST",
        headers={"apikey": key, "Authorization": "Bearer " + key,
                 "Content-Type": "application/json",
                 "Prefer": "resolution=ignore-duplicates,return=minimal"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.status not in (200, 201, 204):
                raise RuntimeError("Unexpected HTTP status")
    except Exception:
        raise RuntimeError("Unified journal upload failed (credentials withheld)") from None


def main():
    p = argparse.ArgumentParser(description="16-strategy demo research journal; dry run unless --commit")
    p.add_argument("--env-file", type=Path, required=True)
    p.add_argument("--commit", action="store_true", help="Explicitly write records to Supabase")
    p.add_argument("--bars", type=int, default=900)
    args = p.parse_args()
    if not 300 <= args.bars <= 3000:
        p.error("--bars must be 300..3000")
    import MetaTrader5 as mt5
    from datetime import datetime, timezone
    if not args.env_file.is_file():
        raise SystemExit("Local .env missing")
    if not mt5.initialize():
        raise SystemExit("MT5 unavailable")
    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError("Verified demo account required")
        load_env(args.env_file)
        if (str(account.login) != os.environ.get("MT5_LOGIN", "").strip()
                or str(account.server) != os.environ.get("MT5_SERVER", "").strip()):
            raise RuntimeError("MT5 account does not match local configuration")
        records = run(mt5, datetime.now(timezone.utc), args.bars, collect_records=True)
        unique = {r["signal_id"]: r for r in records}
        if len(unique) != len(records):
            raise RuntimeError("Duplicate journal IDs detected; refusing upload")
        print(f"Journal candidates={len(records)}; unique={len(unique)}; orders=0")
        if not args.commit:
            print("DRY RUN: no Supabase writes.")
            return
        if not records:
            print("No fresh signals; nothing uploaded.")
            return
        submit_records(records, os.environ.get("SUPABASE_URL", "").strip(),
                       os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip())
        print(f"Submitted {len(records)} journal records; existing IDs ignored; orders=0")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
