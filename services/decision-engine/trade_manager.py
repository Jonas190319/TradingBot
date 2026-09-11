from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from models import ManagementAction, Regime, TradeState


class TradeManager:
    """Tracks open trades and proposes bounded management actions.

    Rules are deliberately conservative: no averaging down, no stop widening,
    and no increase of risk after entry. Adding exposure requires a new trade
    candidate through the full committee/risk process.
    """

    def update(self, trade: TradeState, *, price: float, context: Dict[str, Any]) -> Dict[str, Any]:
        trade.current_price = price
        current_r = trade.r_multiple(price)
        trade.mfe_r = max(trade.mfe_r, current_r)
        trade.mae_r = min(trade.mae_r, current_r)

        action = ManagementAction.HOLD
        reason = "Plan intact"
        new_stop: Optional[float] = None
        reduce_pct = 0.0

        structure_broken = bool(context.get("structure_broken", False))
        severe_news_flip = bool(context.get("severe_news_flip", False))
        regime_invalid = bool(context.get("regime_invalid", False))
        momentum_score = float(context.get("momentum_score", 50.0) or 50.0)

        if structure_broken or severe_news_flip or regime_invalid:
            action = ManagementAction.CLOSE
            reason = "Trade thesis invalidated"
        elif current_r >= 1.0 and momentum_score < 35:
            action = ManagementAction.PARTIAL
            reduce_pct = 0.30
            reason = "Positive trade but momentum deteriorating"
        elif current_r >= 1.5:
            action = ManagementAction.MOVE_SL
            reason = "Protect profit after meaningful favorable excursion"
            # Never loosen risk. Candidate direction handled by comparison.
            if trade.candidate.direction.value == "long":
                proposed = trade.entry_price + 0.35 * abs(trade.entry_price - trade.initial_stop)
                if proposed > trade.current_stop:
                    new_stop = proposed
            else:
                proposed = trade.entry_price - 0.35 * abs(trade.entry_price - trade.initial_stop)
                if proposed < trade.current_stop:
                    new_stop = proposed

        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "trade_id": trade.trade_id,
            "price": price,
            "r": current_r,
            "mfe_r": trade.mfe_r,
            "mae_r": trade.mae_r,
            "action": action.value,
            "reason": reason,
            "new_stop": new_stop,
            "reduce_pct": reduce_pct,
            "context": context,
        }
        trade.actions.append(event)
        if new_stop is not None:
            trade.current_stop = new_stop
        return event

    def close(self, trade: TradeState, *, price: float, ts: Optional[datetime] = None) -> Dict[str, Any]:
        trade.current_price = price
        trade.exit_price = price
        trade.closed_at = ts or datetime.now(timezone.utc)
        trade.realized_r = trade.r_multiple(price)
        trade.mfe_r = max(trade.mfe_r, trade.realized_r)
        trade.mae_r = min(trade.mae_r, trade.realized_r)
        return {
            "trade_id": trade.trade_id,
            "closed_at": trade.closed_at.astimezone(timezone.utc).isoformat(),
            "exit_price": price,
            "realized_r": trade.realized_r,
            "mfe_r": trade.mfe_r,
            "mae_r": trade.mae_r,
            "capture_ratio": (trade.realized_r / trade.mfe_r) if trade.mfe_r > 0 else 0.0,
            "actions": trade.actions,
        }
