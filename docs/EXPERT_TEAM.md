# Expert Team Architecture

## Principle
Specialists do **not** chat freely and do **not** place orders. They emit standardized evidence. A single Portfolio Manager synthesizes the evidence, an independent Risk Manager can veto, and an Execution Agent is the final gate.

## Team
1. **News Analyst** — classifies relevant headlines, sentiment and event severity.
2. **Macro Analyst** — evaluates scheduled economic releases and surprise magnitude.
3. **Technical Analyst** — trend, momentum, breakout and volatility structure.
4. **Quant Analyst** — statistical persistence, recent-vs-baseline return distribution and edge confidence.
5. **Regime Analyst** — NEWS / TREND / RANGE / BREAKOUT / CHAOS classification.
6. **Portfolio Manager** — weighted consensus and quality score; can decide NO TRADE.
7. **Risk Manager** — independent hard veto and position-risk budget.
8. **Execution Agent** — final OFF/SHADOW/DEMO/LIVE safety gate; broker adapter comes later.
9. **Improvement Agent** — research-only performance auditor; produces recommendations, never edits live strategy.

## Communication contract
Every specialist produces an `AgentSignal` with:

`timestamp | symbol | agent_type | direction | confidence | risk_score | recommendation | rationale | payload`

This is intentionally machine-readable so every trade can later be reconstructed and audited.

## Decision chain
`Market + News + Macro + Portfolio State`
→ specialist signals
→ Portfolio Manager
→ Risk Manager
→ Execution Agent
→ broker adapter (not connected yet)

Any strong `NO_TRADE`, CHAOS/NEWS lock, insufficient agreement, quality below threshold, risk-limit breach, or execution-mode block stops the chain.

## Initial capital-protection defaults
These are testable starting values, not promises of profitability:
- minimum quality score: 80/100
- max risk per trade: 0.50% equity
- daily loss stop: 1.50%
- weekly loss stop: 3.00%
- max drawdown stop: 8.00%
- max open portfolio risk: 2.00%
- max open positions: 4
- live execution has a second explicit enable flag
- martingale/grid rescue are prohibited by design

## Strategy lifecycle
`Research → Backtest → Shadow → 4-week Demo → Review → explicit approval → Live`

The currently approved Live version remains unchanged while a candidate is tested in Demo/Shadow. A failed candidate is discarded instead of replacing the stable version.

## Improvement Agent
Every two weeks it should evaluate at least:
- Profit Factor
- expectancy in R
- maximum drawdown
- hit rate
- strategy / symbol / session / regime performance
- spread and slippage
- rejected trades and missed opportunities
- evidence of overtrading or strategy degradation

Recommendations are numbered and evidence-based. They require validation and explicit user approval before any live promotion.

## Important limitation
The current agents are deliberately broker/data-provider agnostic. They are the decision core. MT5, economic-calendar/news feeds, Supabase persistence and the dashboard are connected only after this layer is stable.
