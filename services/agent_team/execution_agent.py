from __future__ import annotations

from dataclasses import dataclass

from .models import Decision, TeamDecision


@dataclass(frozen=True)
class ExecutionPolicy:
    mode: str = "OFF"  # OFF | SHADOW | DEMO | LIVE
    live_execution_enabled: bool = False
    require_stop_loss: bool = True
    max_slippage_points: float = 30.0


@dataclass(frozen=True)
class ExecutionIntent:
    executable: bool
    mode: str
    symbol: str | None
    side: str | None
    risk_pct: float
    reason: str


class ExecutionAgent:
    """Final gate. Produces an execution intent only; broker integration is added later."""

    name = "execution"

    def __init__(self, policy: ExecutionPolicy | None = None) -> None:
        self.policy = policy or ExecutionPolicy()

    def prepare(self, decision: TeamDecision) -> ExecutionIntent:
        mode = self.policy.mode.upper()
        if mode == "OFF":
            return ExecutionIntent(False, mode, None, None, 0.0, "Global trading mode is OFF.")
        if not decision.executable or decision.proposal is None:
            return ExecutionIntent(False, mode, decision.symbol, None, 0.0, "Team decision is not executable.")
        if decision.risk_verdict.decision != Decision.APPROVE:
            return ExecutionIntent(False, mode, decision.symbol, None, 0.0, "Risk manager did not approve.")
        if mode == "LIVE" and not self.policy.live_execution_enabled:
            return ExecutionIntent(False, mode, decision.symbol, None, 0.0, "Live execution requires a separate explicit enable flag.")
        if mode not in {"SHADOW", "DEMO", "LIVE"}:
            return ExecutionIntent(False, mode, decision.symbol, None, 0.0, "Unknown execution mode.")

        return ExecutionIntent(
            True,
            mode,
            decision.proposal.symbol,
            decision.proposal.direction.value,
            decision.risk_verdict.approved_risk_pct,
            "Approved by portfolio manager, risk manager and execution gate.",
        )
