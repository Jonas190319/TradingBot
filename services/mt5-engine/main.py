import time
import argparse
import sys
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from typing import Dict, Iterable, Optional

import MetaTrader5 as mt5
from supabase import create_client

from config import load_settings

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from market_features import bars_from_rates
from broker_clock import timestamp_utc, closed_history_mode
from shadow_runtime import ShadowRuntime

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
        )
    ).lower()
    if not settings.expected_broker.strip() or settings.expected_broker.lower() not in broker_text:
        raise RuntimeError(
            f"Broker safety check failed: expected {settings.expected_broker!r}, "
            f"connected server={account.server!r}, company={getattr(account, 'company', '')!r}"
        )

    if account.login != settings.mt5_login or account.server != settings.mt5_server:
        raise RuntimeError("Connected MT5 account does not match configured login/server")

    # This milestone always requires demo, regardless of environment overrides.
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


def publish_tick(sb, logical_name: str, broker_symbol: str, max_age=60, time_mode='utc'):
    info = mt5.symbol_info(broker_symbol)
    tick = mt5.symbol_info_tick(broker_symbol)
    if info is None or tick is None:
        return None

    values = (float(tick.bid), float(tick.ask), float(info.point))
    if not all(isfinite(x) and x > 0 for x in values) or tick.ask < tick.bid:
        return None
    now = datetime.now(timezone.utc)
    raw_seconds = getattr(tick, 'time_msc', 0)/1000 or tick.time
    ts = timestamp_utc(raw_seconds, time_mode)
    # Permit only two seconds of clock jitter, never an hourly future timestamp.
    if not -2 <= (now-ts).total_seconds() <= max_age:
        return None

    point = info.point or 0
    spread_points = ((tick.ask - tick.bid) / point) if point else None
    sb.table("market_context").insert(
        {
            "ts": ts.isoformat(),
            "symbol": logical_name,
            "bid": tick.bid,
            "ask": tick.ask,
            "spread_points": spread_points,
            "regime": "unknown",
            "source": f"pepperstone-mt5-demo:{broker_symbol}",
            "technical_context": {'raw_mt5_time_seconds': raw_seconds,
                                  'timestamp_mode': time_mode, 'timestamp_normalized': True},
        }
    ).execute()
    return ts, float(tick.bid), float(tick.ask), float(info.point)


def main(once=False) -> None:
    settings = load_settings()
    sb = create_client(settings.supabase_url, settings.supabase_service_role_key)
    initialize_mt5(settings)

    try:
        account = verify_account(settings)
        universe = resolve_universe()
        runtime = ShadowRuntime(sb, f'{account.server}:{account.login}') if settings.shadow_analysis_enabled else None
        if runtime:
            runtime.restore_tracking()

        print(
            "Connected safely to Pepperstone MT5 Demo "
            f"login={account.login}, server={account.server}, "
            f"balance={account.balance:.2f} {account.currency}"
        )
        print(f"Resolved symbols: {universe}")
        print(f'Timestamp modes: ticks={settings.mt5_tick_time_mode}; bars={settings.mt5_bar_time_mode}; stored timestamps=UTC')
        print('Execution remains disabled. SHADOW analysis=' + ('ON' if runtime else 'OFF'))
        print('News/calendar feed missing; funding veto active; no automatic orders.')
        last_history_check = {}
        heartbeat = 0

        while True:
            account = verify_account(settings)
            positions = mt5.positions_get()
            fresh = 0
            failed = 0
            analysed = 0
            for logical_name, broker_symbol in universe.items():
                try:
                    quote = publish_tick(sb, logical_name, broker_symbol, settings.max_tick_age_seconds,
                                         settings.mt5_tick_time_mode)
                    if quote is None:
                        continue
                    fresh += 1
                    ts, bid, ask, point = quote
                    if runtime:
                        runtime.observe(logical_name, ts, bid, ask)
                        checked = last_history_check.get(logical_name, 0)
                        if time.monotonic()-checked < 30:
                            continue
                        last_history_check[logical_name] = time.monotonic()
                        now = datetime.now(timezone.utc)
                        rates = mt5.copy_rates_from_pos(broker_symbol, mt5.TIMEFRAME_M5, 1, 600)
                        bar_mode = closed_history_mode(rates, now, settings.mt5_bar_time_mode)
                        bars = bars_from_rates(rates, now, bar_mode)
                        if not bars:
                            raise ValueError('MT5 returned no closed M5 history')
                        result = runtime.evaluate(logical_name, now, bid, ask, point, bars, account,
                                                  len(positions) if positions is not None else -1)
                        if result:
                            analysed += 1
                            print(f"SHADOW {logical_name}: {result['signals']} agents; {result['candidates']} candidates; regime={result['regime']}; bar_time={bar_mode}; orders=0", flush=True)
                except ValueError as exc:
                    failed += 1
                    print(f'{logical_name}: analysis skipped: {exc}', flush=True)
                except Exception as exc:
                    failed += 1
                    # Do not print client configuration, passwords or request headers.
                    print(f'{logical_name}: persistence/analysis error {type(exc).__name__}; retrying; orders=0', flush=True)
            if time.monotonic()-heartbeat >= 60:
                print(f'Heartbeat {utc_now()}: fresh_quotes={fresh}/{len(universe)}, orders=0', flush=True)
                heartbeat = time.monotonic()
            if once:
                if failed or not fresh or (runtime and not analysed):
                    raise RuntimeError('One-cycle diagnostic incomplete; check per-symbol messages. No orders sent.')
                break
            time.sleep(settings.telemetry_interval_seconds)
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Pepperstone demo telemetry and SHADOW agents; no orders')
    parser.add_argument('--once', action='store_true', help='Run one collection/analysis cycle and exit')
    main(once=parser.parse_args().once)
