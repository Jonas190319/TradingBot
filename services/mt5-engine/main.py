import time
from datetime import datetime, timezone
import MetaTrader5 as mt5
from supabase import create_client
from config import load_settings

SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "DAX40", "NAS100"]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def initialize_mt5(settings):
    ok = mt5.initialize(
        path=settings.mt5_terminal_path,
        login=settings.mt5_login,
        password=settings.mt5_password,
        server=settings.mt5_server,
    )
    if not ok:
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")


def main():
    settings = load_settings()
    sb = create_client(settings.supabase_url, settings.supabase_service_role_key)
    initialize_mt5(settings)

    account = mt5.account_info()
    if account is None:
        raise RuntimeError(f"No MT5 account info: {mt5.last_error()}")

    # Engine is intentionally telemetry-only at milestone 1.
    # No order_send call exists here yet.
    print(f"Connected to MT5 login={account.login}, server={account.server}")

    while True:
        for symbol in SYMBOLS:
            info = mt5.symbol_info(symbol)
            if info is None:
                continue
            if not info.visible:
                mt5.symbol_select(symbol, True)
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                continue
            point = info.point or 0
            spread_points = ((tick.ask - tick.bid) / point) if point else None
            sb.table("market_context").insert({
                "ts": utc_now(),
                "symbol": symbol,
                "bid": tick.bid,
                "ask": tick.ask,
                "spread_points": spread_points,
                "regime": "unknown",
                "source": "mt5-demo"
            }).execute()
        time.sleep(5)


if __name__ == "__main__":
    main()
