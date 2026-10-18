"""Deterministic, offline research signal journal records for all 16 strategies.

No MT5 connection, network access, credentials, or order execution.
IDs intentionally exclude volatile candidate UUIDs, quote-derived entry, and score.
"""
from datetime import datetime, timezone
from hashlib import sha256
from math import isfinite

from research_strategy_registry import MARKETS, STRATEGIES


def journal_record(*, account_server, account_login, market, broker_symbol,
                   strategy, side, bar_time_utc, entry, stop_loss, take_profit,
                   source, score=None, metadata=None):
    if market not in MARKETS or strategy not in STRATEGIES:
        raise ValueError("Unregistered market or strategy")
    if source not in ("shadow_strategist", "profile_scanner"):
        raise ValueError("Unknown research source")
    if (strategy in STRATEGIES[:13]) != (source == "shadow_strategist"):
        raise ValueError("Strategy/source mismatch")
    if side not in ("long", "short"):
        raise ValueError("Invalid side")
    if not account_server or not broker_symbol or not str(account_login).isdigit():
        raise ValueError("Missing account/broker identity")
    if not isinstance(bar_time_utc, datetime) or bar_time_utc.tzinfo is None:
        raise ValueError("Bar time must be timezone-aware")
    ts = bar_time_utc.astimezone(timezone.utc)
    if ts.second or ts.microsecond or ts.minute % 5:
        raise ValueError("Expected M5 opening timestamp")
    entry, stop_loss, take_profit = map(float, (entry, stop_loss, take_profit))
    if not all(map(isfinite, (entry, stop_loss, take_profit))):
        raise ValueError("Non-finite prices")
    if side == "long" and not stop_loss < entry < take_profit:
        raise ValueError("Invalid long risk geometry")
    if side == "short" and not take_profit < entry < stop_loss:
        raise ValueError("Invalid short risk geometry")
    if score is not None and (not isfinite(float(score)) or not 0 <= float(score) <= 100):
        raise ValueError("Invalid heuristic score")
    # A deterministic signal is unique per account, market, bar, strategy and side.
    identity = "|".join((str(account_server), str(account_login), market,
                         ts.isoformat(), strategy, side))
    return {
        "signal_id": sha256(identity.encode("utf-8")).hexdigest(),
        "account_server": str(account_server),
        "account_login": int(account_login),
        "symbol": market,
        "broker_symbol": broker_symbol,
        "strategy": strategy,
        "side": side,
        "bar_time_utc": ts.isoformat(),
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "source": source,
        "setup_score": None if score is None else float(score),
        "metadata": metadata or {},
    }


def records_from_scan(account_server, account_login, broker_symbol, market, bar_time_utc,
                      existing, profile_signals):
    """Transform one unified scanner observation; caller supplies its CLOSED M5 bar timestamp.

    'existing' is the 13-strategist result mapping (strategy -> candidate dict/None).
    'profile_signals' is the list of three-strategy profile signal dicts.
    """
    out = []
    for strategy, candidate in existing.items():
        if candidate is None:
            continue
        out.append(journal_record(
            account_server=account_server, account_login=account_login,
            market=market, broker_symbol=broker_symbol, strategy=strategy,
            side=candidate["side"], bar_time_utc=bar_time_utc,
            entry=candidate["entry"], stop_loss=candidate["stop"],
            take_profit=candidate["target"], source="shadow_strategist",
            score=candidate.get("score")))
    for signal in profile_signals:
        out.append(journal_record(
            account_server=account_server, account_login=account_login,
            market=market, broker_symbol=broker_symbol, strategy=signal["strategy"],
            side=signal["side"], bar_time_utc=bar_time_utc,
            entry=signal["entry"], stop_loss=signal["stop"],
            take_profit=signal["target"], source="profile_scanner"))
    ids = [row["signal_id"] for row in out]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate signals within the same M5 observation")
    return out
