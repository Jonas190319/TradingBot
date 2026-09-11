# Decision Engine

This service contains the trading expert-team logic and is deliberately separated from MT5 execution.

## Core strategists

1. **Opening Range** — opening-range breakout/retest logic.
2. **Trend Pullback** — continuation after a controlled pullback inside a confirmed trend.
3. **Compression Breakout** — volatility contraction followed by expansion.
4. **Liquidity Sweep** — failed breakout / sweep-and-reject reversal.

Each strategist returns a complete `TradeCandidate`: direction, entry, SL, TP1/TP2, setup score, invalidation and management plan.

## Decision sequence

`Market snapshot -> regime/analyst views -> 4 strategists -> portfolio committee -> risk manager -> execution boundary`

A strategist proposes; it never sends an order. The portfolio committee ranks candidates and assigns a funding class. The independent risk manager may reduce size or reject a candidate for portfolio, drawdown, spread/slippage or loss-limit reasons.

## Pre-trade learning

`PreTradeRecorder` records the setup before entry. For every candidate it keeps:
- market features and price context,
- setup-score progression,
- qualification stage,
- committee decision,
- risk decision,
- timestamps and reasons.

This lets the learning layer compare not only the final entry state, but how a setup developed. A rising score into entry can later be tested against a deteriorating score into entry.

## In-trade learning

`TradeManager` tracks:
- current R-multiple,
- MFE (maximum favorable excursion),
- MAE (maximum adverse excursion),
- each HOLD / PARTIAL / MOVE_SL / CLOSE action,
- context at the time of each action.

Hard rule: risk may not be increased after entry. No averaging down, martingale or stop widening. Additional exposure must be proposed as a new candidate and pass the full committee/risk process.

## Counterfactual / shadow learning

Rejected and unexecuted candidates are still followed as shadow outcomes. `LearningEngine` compares executed vs. rejected opportunities and calculates expectancy, profit factor, MFE/MAE and capture ratio by:

`strategy x symbol x regime x session`

This is used for Opportunity Audit and exit-management review. It does **not** autonomously change live rules.

## Promotion path

Any rule/weight/threshold change must follow:

`research/backtest -> replay/walk-forward -> shadow -> demo -> explicit human approval -> live`

The decision engine is therefore safe to develop before any broker account is connected.
