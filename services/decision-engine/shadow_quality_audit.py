"""Read-only quality gates for sampled SHADOW research outcomes.

These checks never approve orders or modify strategy parameters.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from math import isfinite


def _utc(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def audit_shadow_outcomes(rows, min_sample=30):
    """Return descriptive statistics and data-quality warnings, never trade permission.

    Rows may be raw Supabase shadow_outcomes records. Only completed, finite
    virtual outcomes are summarized. Duplicates are excluded by candidate_id.
    The result intentionally does not infer fill prices, transaction costs,
    slippage, or real-world expectancy from sampled quotes.
    """
    groups = defaultdict(list)
    excluded = Counter()
    seen = set()
    for row in rows:
        candidate_id = row.get("candidate_id")
        if not candidate_id or candidate_id in seen:
            excluded["missing_or_duplicate_candidate_id"] += 1
            continue
        seen.add(candidate_id)
        if row.get("was_executed") is not False:
            excluded["not_explicitly_shadow"] += 1
            continue
        if not _utc(row.get("completed_at")):
            excluded["missing_or_invalid_completion"] += 1
            continue
        try:
            r = float(row["realized_r"])
        except (ValueError, TypeError, KeyError):
            excluded["missing_or_invalid_r"] += 1
            continue
        if not isfinite(r):
            excluded["nonfinite_r"] += 1
            continue
        metadata = row.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        strategy = row.get("strategy")
        symbol = row.get("symbol")
        if not strategy or not symbol:
            excluded["missing_strategy_or_symbol"] += 1
            continue
        groups[(strategy, symbol)].append((r, metadata, row))

    results = []
    for (strategy, symbol), samples in sorted(groups.items()):
        values = [x[0] for x in samples]
        n = len(values)
        wins = sum(r > 0 for r in values)
        gross_profit = sum(max(0.0, r) for r in values)
        gross_loss = -sum(min(0.0, r) for r in values)
        warnings = ["sampled_quotes_not_real_fills", "costs_and_slippage_unverified",
                    "intrabar_path_unknown", "entry_fill_not_verified"]
        if n < min_sample:
            warnings.append("insufficient_sample")
        if any(x[1].get("resumed_after_restart") for x in samples):
            warnings.append("tracking_resumed_after_restart")
        if any(x[1].get("exit_reason") == "horizon_expired" for x in samples):
            warnings.append("horizon_expiry_mark_to_market")
        if any(x[1].get("sampled") is not True for x in samples):
            warnings.append("sampling_provenance_missing")
        results.append({
            "strategy": strategy, "symbol": symbol, "n": n,
            "wins": wins, "hit_rate": wins / n,
            "mean_r": sum(values) / n, "total_r": sum(values),
            "profit_factor": gross_profit / gross_loss if gross_loss else None,
            "profit_factor_unbounded": gross_loss == 0 and gross_profit > 0,
            "research_only": True, "eligible_for_auto_tuning": False,
            "eligible_for_execution": False, "warnings": warnings,
        })
    return {"groups": results, "excluded": dict(excluded),
            "research_only": True, "eligible_for_execution": False}
