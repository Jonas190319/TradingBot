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

Specialists communicate through one machine-readable `AgentSignal` contract. They do not place trades individually. Strategists create complete trade plans; the Portfolio Committee ranks them; the Risk Manager sizes or vetoes them; the Execution Agent remains the final broker boundary.

See [`docs/EXPERT_TEAM.md`](docs/EXPERT_TEAM.md) for the governance model and [`services/decision-engine/README.md`](services/decision-engine/README.md) for the strategy/learning workflow.

## Four focused strategists
1. **Opening Range** — breakout/retest around the daily cash-market opening.
2. **Trend Pullback** — continuation after a controlled pullback in a confirmed trend.
3. **Compression Breakout** — low-volatility contraction followed by expansion.
4. **Liquidity Sweep** — failed breakout / sweep-and-reject reversal.

Each strategist outputs: direction, entry, SL, TP1/TP2, setup score, invalidation and a predefined management plan.

## Learning architecture
The system tracks the full decision lifecycle:

`pre-trade formation -> candidate -> committee -> risk -> in-trade management -> exit -> post-trade audit`

Pre-trade setup development is recorded before entry, including score progression and market context. During a trade, MFE, MAE, R-multiple and every management action are recorded. Rejected candidates continue in Shadow so the system can measure whether filters were too strict or correctly avoided bad trades.

Learning is evaluated by `strategy x symbol x regime x session`. The Improvement layer can recommend changes, but it cannot alter live rules automatically.

## Architecture
- **Vercel / Next.js dashboard** — monitoring and control surface
- **Supabase** — accounts, strategy versions, signals, decisions, trades, pre-trade events, management events, shadow outcomes, metrics and improvement reports
- **Windows VPS / Python** — expert team + later MetaTrader 5 bridge
- **GitHub** — source control and deployment source

## Safety model
- Global trading mode starts at `OFF`.
- Live execution is separately gated by `live_execution_enabled=false`.
- `NO_TRADE` is a first-class decision.
- Risk Manager has hard-veto authority.
- No martingale, grid rescue, averaging down or stop widening after entry.
- Additional exposure must be a new trade proposal and pass the complete process again.
- Candidate strategy changes follow Research -> Backtest/Replay -> Shadow -> 4-week Demo -> explicit approval -> Live.
- Improvement Agent never edits the live strategy automatically.

## Initial test universe
EURUSD, GBPUSD, USDJPY, XAUUSD, DAX40, NAS100.

## Decision-core source
- `services/agent_team/` — expert roles and governance
- `services/decision-engine/` — four strategists, committee, pre-trade recorder, risk, trade management and learning
- `supabase/learning_schema.sql` — persistence schema extension for learning events

## Next milestones
1. Wire the decision-engine persistence adapter to the existing Supabase project.
2. Add historical replay/backtest and walk-forward runner.
3. Build dashboard timelines for pre-trade, in-trade and shadow decisions.
4. Connect news/economic-calendar feeds.
5. Connect Trive MT5 Demo/Live only after the complete decision system has been validated.

## Environment variables
Copy `.env.example` to the relevant runtime environment. Never commit broker passwords, private API keys or Supabase service-role secrets.
