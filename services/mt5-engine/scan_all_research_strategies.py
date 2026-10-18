"""Unified, read-only 16-strategy x 8-market diagnostic.

Existing 13 strategists are evaluated independently (before committee/risk veto);
the three profile strategies use their own scanner. No Supabase writes or order API.
This is NOT a trade execution or backtest result.
"""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research_strategy_registry import EXISTING, MARKETS, NEW, validate_inventory
from scan_vwap_profile_markets import scan_symbol
from market_features import bars_from_rates, build_features
from services.decision_engine.models import MarketSnapshot, Regime
from services.decision_engine.strategists import CORE_STRATEGISTS


def evaluate_existing(logical, rates, now, bid, ask):
    bars = bars_from_rates(rates, now, "utc")
    features = build_features(logical, now, bars)
    # Research-only heuristic regime, not the live agent team's regime verdict.
    # Do not silently treat this as committee approval or calibrated confidence.
    if features["adx"] >= 30 and abs(features["trend_alignment"] - 50) >= 10:
        regime = Regime.TREND
    elif features["compression_score"] >= 55:
        regime = Regime.BREAKOUT
    else:
        regime = Regime.RANGE
    snapshot = MarketSnapshot(now, logical, bid, ask, ask - bid, features)
    results = {}
    for strategist in CORE_STRATEGISTS:
        candidate = strategist.evaluate(snapshot, regime)
        results[strategist.name] = None if candidate is None else {
            "side": candidate.direction.value,
            "entry": candidate.entry,
            "stop": candidate.stop_loss,
            "target": candidate.take_profit_1,
            "score": candidate.setup_score,
        }
    return results, regime.value


def run(mt5, now, bars_count=900):
    from main import SYMBOL_ALIASES
    validate_inventory((s.name for s in CORE_STRATEGISTS), NEW, SYMBOL_ALIASES)
    print(f"Coverage: {len(EXISTING) + len(NEW)} strategies x {len(MARKETS)} markets = 128 checks; orders=0")
    account = mt5.account_info()
    if account is None or getattr(account, "trade_mode", None) != mt5.ACCOUNT_TRADE_MODE_DEMO:
        raise RuntimeError("Read-only scanner requires a verified demo account")
    for logical in MARKETS:
        broker = next((s for s in SYMBOL_ALIASES[logical] if mt5.symbol_info(s) is not None), None)
        if broker is None:
            print(f"{logical}: unavailable; evaluated=0/16")
            continue
        try:
            # Shared fresh-data guard. Avoid evaluating stale weekend bars.
            rates = mt5.copy_rates_from_pos(broker, mt5.TIMEFRAME_M5, 1, bars_count)
            if rates is None or len(rates) < 60:
                print(f"{logical}: insufficient_history; evaluated=0/16")
                continue
            latest = max(datetime.fromtimestamp(int(r["time"]), timezone.utc) for r in rates)
            if latest + timedelta(minutes=5) > now or now - (latest + timedelta(minutes=5)) > timedelta(minutes=20):
                print(f"{logical}: market_closed_or_stale; evaluated=0/16; last_closed_utc={latest.isoformat()}")
                continue
            tick = mt5.symbol_info_tick(broker)
            if tick is None or not 0 < float(tick.bid) <= float(tick.ask):
                print(f"{logical}: missing_quote; evaluated=0/16")
                continue
            existing, regime = evaluate_existing(logical, rates, now, float(tick.bid), float(tick.ask))
            profile = scan_symbol(mt5, logical, broker, now, bars_count)
            if profile["status"] == "ok":
                profile_signals = profile["signals"]
                profile_results = {s: [x for x in profile_signals if x["strategy"] == s] for s in NEW}
                print(f"{logical}: evaluated=16/16; regime_heuristic={regime}; profile=ok; "
                      f"candidates={sum(v is not None for v in existing.values()) + len(profile_signals)}; orders=0")
            else:
                profile_results = {s: [] for s in NEW}
                print(f"{logical}: evaluated=13/16; profile={profile['status']}; "
                      f"regime_heuristic={regime}; candidates={sum(v is not None for v in existing.values())}; orders=0")
            for strategy, result in existing.items():
                if result is not None:
                    print(f"  {strategy}: {result['side']} entry={result['entry']} stop={result['stop']} target={result['target']}")
            for strategy, signals in profile_results.items():
                for signal in signals:
                    print(f"  {strategy}: {signal['side']} entry={signal['entry']} stop={signal['stop']} target={signal['target']}")
        except (ValueError, RuntimeError) as exc:
            print(f"{logical}: skipped ({type(exc).__name__}: {exc}); orders=0")
        except Exception as exc:
            print(f"{logical}: error={type(exc).__name__}; orders=0")


def main():
    parser = argparse.ArgumentParser(description="Read-only unified strategy research; no orders or database writes")
    parser.add_argument("--bars", type=int, default=900)
    args = parser.parse_args()
    if not 300 <= args.bars <= 3000:
        parser.error("--bars must be 300..3000")
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise SystemExit("MT5 unavailable")
    try:
        run(mt5, datetime.now(timezone.utc), args.bars)
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
