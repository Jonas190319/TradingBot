"""Explicit, opt-in research signal uploader. No broker orders; dry run by default."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import urllib.request

from import_mt5_history import load_env
from scan_vwap_profile_markets import scan_symbol


def main():
    p = argparse.ArgumentParser(description="MT5 read-only signal journal; default dry-run")
    p.add_argument("--commit", action="store_true")
    p.add_argument("--env-file", type=Path, required=True)
    args = p.parse_args()
    import MetaTrader5 as mt5
    from main import SYMBOL_ALIASES
    from datetime import datetime, timezone
    if not mt5.initialize():
        raise SystemExit("MT5 unavailable")
    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError("Demo account required")
        if not args.env_file.is_file():
            raise RuntimeError("Local .env missing")
        load_env(args.env_file)
        if str(account.login) != os.environ.get("MT5_LOGIN", "").strip() or str(account.server) != os.environ.get("MT5_SERVER", "").strip():
            raise RuntimeError("MT5 account does not match local configuration")
        now = datetime.now(timezone.utc)
        records = []
        for logical, aliases in SYMBOL_ALIASES.items():
            broker = next((s for s in aliases if mt5.symbol_info(s) is not None), None)
            if broker is None:
                print(f"{logical}: unavailable")
                continue
            result = scan_symbol(mt5, logical, broker, now)
            print(f"{logical}: {result['status']}; signals={len(result.get('signals', []))}")
            if result["status"] != "ok":
                continue
            for s in result["signals"]:
                identity = "|".join((str(account.server), str(account.login), logical,
                                     result["last_closed_utc"], s["strategy"], s["side"]))
                records.append(dict(
                    signal_id=hashlib.sha256(identity.encode()).hexdigest(),
                    account_server=str(account.server), account_login=int(account.login),
                    symbol=logical, broker_symbol=broker, strategy=s["strategy"], side=s["side"],
                    bar_time_utc=result["last_closed_utc"], prior_day=result["prior_day"],
                    entry=s["entry"], stop_loss=s["stop"], take_profit=s["target"],
                    vah=result["vah"], poc=result["poc"], val=result["val"]))
        print(f"Signals found: {len(records)}; orders=0")
        if not args.commit:
            print("DRY RUN: nothing uploaded.")
            return
        if not records:
            print("No new research signals to upload.")
            return
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not url.startswith("https://") or not key:
            raise RuntimeError("Supabase configuration missing")
        request = urllib.request.Request(
            url.rstrip("/") + "/rest/v1/mt5_research_signals?on_conflict=signal_id",
            data=json.dumps(records, allow_nan=False).encode("utf-8"), method="POST",
            headers={"apikey": key, "Authorization": "Bearer " + key,
                     "Content-Type": "application/json",
                     "Prefer": "resolution=ignore-duplicates,return=minimal"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                if response.status not in (200, 201, 204):
                    raise RuntimeError("Unexpected HTTP status")
        except Exception:
            raise RuntimeError("Research journal upload failed (credentials withheld)") from None
        print(f"Submitted {len(records)} research signals; duplicates ignored; orders=0")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
