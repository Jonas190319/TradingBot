# Trading Bot

Decision core for a Trive / MetaTrader 5 trading system.

## Current state
The **expert-team decision layer is implemented and broker-agnostic**. MT5, news feeds and live execution are intentionally connected later.

## Expert team
- News Analyst
- Macro Analyst
- Technical Analyst
- Quant Analyst
- Regime Analyst
- Portfolio Manager
- independent Risk Manager
- Execution Agent
- Improvement Agent

Specialists communicate through one machine-readable `AgentSignal` contract. They do not place trades individually. The Portfolio Manager proposes a trade, the Risk Manager can veto it, and the Execution Agent is the final gate.

See [`docs/EXPERT_TEAM.md`](docs/EXPERT_TEAM.md) for the full governance model.

## Architecture
- **Vercel / Next.js dashboard** — monitoring and control surface
- **Supabase** — accounts, strategy versions, signals, decisions, trades, metrics and improvement reports
- **Windows VPS / Python** — expert team + later MetaTrader 5 bridge
- **GitHub** — source control and deployment source

## Safety model
- Global trading mode starts at `OFF`.
- Live execution is separately gated by `live_execution_enabled=false`.
- `NO_TRADE` is a first-class decision.
- Risk Manager has hard-veto authority.
- No martingale and no grid rescue.
- Candidate strategy changes follow Research -> Backtest -> Shadow -> 4-week Demo -> explicit approval -> Live.
- Improvement Agent never edits the live strategy automatically.

## Initial test universe
EURUSD, GBPUSD, USDJPY, XAUUSD, DAX40, NAS100.

## Decision-core source
`services/agent_team/`

The current source contains standardized domain models, all nine team roles, orchestration, capital-protection policy and safety tests.

## Next milestones
1. Add persistence adapter from team outputs to Supabase.
2. Add historical/backtest runner.
3. Build dashboard views for agents, decisions, vetoes and performance.
4. Connect news/economic-calendar feeds.
5. Connect Trive MT5 Demo only after credentials are available.
6. Keep Live blocked until Demo/Shadow validation and explicit approval.

## Environment variables
Copy `.env.example` to the relevant runtime environment. Never commit broker passwords, private API keys or Supabase service-role secrets.
