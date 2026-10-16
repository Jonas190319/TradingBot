"""Read-only risk sizing research. No broker access or order submission."""
from dataclasses import dataclass
from math import floor, isfinite


@dataclass(frozen=True)
class SizingDecision:
    approved: bool
    lots: float
    risk_amount: float
    reason: str


def size_candidate(*, equity: float, entry: float, stop_loss: float,
                   tick_size: float, tick_value_per_lot: float,
                   min_lot: float, max_lot: float, lot_step: float,
                   free_margin: float, margin_per_lot: float,
                   open_positions: int, existing_open_risk: float,
                   risk_pct: float = 0.5, max_total_risk_pct: float = 1.5,
                   max_positions: int = 5) -> SizingDecision:
    """Fail closed; all monetary inputs are in account currency.

    tick_value_per_lot must be the broker-verified loss-side tick value
    for one lot in account currency. Costs/slippage are NOT included;
    this is not an execution authorization.
    """
    reject = lambda reason: SizingDecision(False, 0.0, 0.0, reason)
    values = (equity, entry, stop_loss, tick_size, tick_value_per_lot,
              min_lot, max_lot, lot_step, free_margin, margin_per_lot,
              existing_open_risk, risk_pct, max_total_risk_pct)
    if any(not isinstance(v, (int, float)) or not isfinite(v) for v in values):
        return reject("invalid_numeric_input")
    if (equity <= 0 or entry <= 0 or stop_loss <= 0 or entry == stop_loss
            or tick_size <= 0 or tick_value_per_lot <= 0 or min_lot <= 0
            or max_lot < min_lot or lot_step <= 0 or free_margin < 0
            or margin_per_lot <= 0 or existing_open_risk < 0
            or not 0 < risk_pct <= 0.5
            or not 0 < max_total_risk_pct <= 1.5):
        return reject("invalid_risk_or_broker_limits")
    if not isinstance(open_positions, int) or isinstance(open_positions, bool) or open_positions < 0:
        return reject("invalid_position_count")
    if open_positions >= max_positions:
        return reject("max_positions_reached")
    remaining = equity * max_total_risk_pct / 100 - existing_open_risk
    budget = min(equity * risk_pct / 100, remaining)
    if budget <= 0:
        return reject("total_risk_limit_reached")
    loss_per_lot = abs(entry - stop_loss) / tick_size * tick_value_per_lot
    raw_lots = min(budget / loss_per_lot, free_margin / margin_per_lot, max_lot)
    # Quantize downward from zero, never round up the proposed risk.
    steps = floor((raw_lots + 1e-12) / lot_step)
    lots = round(steps * lot_step, 10)
    if lots < min_lot:
        return reject("below_minimum_lot_or_margin")
    risk = lots * loss_per_lot
    if risk > budget + 1e-8 or lots > max_lot + 1e-10:
        return reject("sizing_exceeds_limits")
    return SizingDecision(True, lots, risk, "research_only_not_execution_approval")
