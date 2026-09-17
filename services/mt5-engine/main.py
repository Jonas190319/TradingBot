import time
from datetime import datetime, timezone
from typing import Dict, Iterable, Optional

import MetaTrader5 as mt5
from supabase import create_client

from config import load_settings

# Logical market names used by the decision engine -> Pepperstone/MT5 aliases.
# We resolve aliases at startup so broker naming differences do not leak into agents.
SYMBOL_ALIASES: Dict[str, Iterable[str]] = {
    "EURUSD": ("EURUSD",),
    "GBPUSD": ("GBPUSD",),
    "USDJPY": ("USDJPY",),
    "XAUUSD": ("XAUUSD",),
    "GER40": ("GER40", "DAX40", "DE40"),
    "NAS100": ("NAS100", "USTEC", "US100"),
    "US500": ("US500", "SPX500", "US500.cash"),
    "US30": ("US30", "DJ30", "WS30"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_mt5(settings) -> None:
    ok = mt5.initialize(
        path=settings.mt5_terminal_path,
        login=settings.mt5_login,
        password=settings.mt5_password,
        server=settings.mt5_server,
    )
    if not ok:
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")


def verify_account(settings):
    account = mt5.account_info()
    if account is None:
        raise RuntimeError(f"No MT5 account info: {mt5.last_error()}")

    broker_text = " ".join(
        str(value or "")
        for value in (
            getattr(account, "company", ""),
            getattr(account, "server", ""),
            settings.mt5_account_label,
        )
    ).lower()
    if settings.expected_broker.lower() not in broker_text:
        raise RuntimeError(
            f"Broker safety check failed: expected {settings.expected_broker!r}, "
            f"connected server={account.server!r}, company={getattr(account, 'company', '')!r}"
        )

    if settings.require_demo_account:
        demo_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0)
        if getattr(account, "trade_mode", None) != demo_mode:
            raise RuntimeError(
                "Demo safety check failed. Refusing to run against a non-demo MT5 account."
            )

    return account


def resolve_symbol(aliases: Iterable[str]) -> Optional[str]:
    for symbol in aliases:
        info = mt5.symbol_info(symbol)
        if info is None:
            continue
        if not info.visible and not mt5.symbol_select(symbol, True):
            continue
        return symbol
    return None


def resolve_universe() -> Dict[str, str]:
    resolved: Dict[str, str] = {}
    missing = []
    for logical_name, aliases in SYMBOL_ALIASES.items():
        symbol = resolve_symbol(aliases)
        if symbol:
            resolved[logical_name] = symbol
        else:
            missing.append(logical_name)

    if missing:
        print(f"Warning: unavailable symbols skipped: {', '.join(missing)}")
    if not resolved:
        raise RuntimeError("No configured trading symbols are available in MT5.")
    return resolved


def publish_tick(sb, logical_name: str, broker_symbol: str) -> None:
    info = mt5.symbol_info(broker_symbol)
    tick = mt5.symbol_info_tick(broker_symbol)
    if info is None or tick is None:
        return

    point = info.point or 0
    spread_points = ((tick.ask - tick.bid) / point) if point else None
    sb.table("market_context").insert(
        {
            "ts": utc_now(),
            "symbol": logical_name,
            "bid": tick.bid,
            "ask": tick.ask,
            "spread_points": spread_points,
            "regime": "unknown",
            "source": f"pepperstone-mt5-demo:{broker_symbol}",
        }
    ).execute()


def main() -> None:
    settings = load_settings()
    sb = create_client(settings.supabase_url, settings.supabase_service_role_key)
    initialize_mt5(settings)

    try:
        account = verify_account(settings)
        universe = resolve_universe()

        print(
            "Connected safely to Pepperstone MT5 Demo "
            f"login={account.login}, server={account.server}, "
            f"balance={account.balance:.2f} {account.currency}"
        )
        print(f"Resolved symbols: {universe}")
        print("Execution remains disabled in this bridge; telemetry only.")

        while True:
            for logical_name, broker_symbol in universe.items():
                publish_tick(sb, logical_name, broker_symbol)
            time.sleep(settings.telemetry_interval_seconds)
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
