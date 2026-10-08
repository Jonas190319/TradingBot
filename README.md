# Trading Bot

Pepperstone MetaTrader 5 demo market data, nine expert roles and four strategy modules with Supabase persistence. The Windows bridge runs in **SHADOW mode only** and contains no broker order API.

## Current integration

`services/mt5-engine/main.py` collects fresh quotes and up to 600 closed M5 bars for EURUSD, GBPUSD, USDJPY, XAUUSD, GER40, NAS100, US500 and US30. Broker aliases are resolved at startup. It verifies the configured Pepperstone demo account at startup and on every cycle, rejecting real accounts regardless of environment overrides.

Each new closed bar runs News, Macro, Technical, Quant and Regime analysis, the four strategists, committee/risk review, portfolio allocation and execution/improvement reports. Nine standardized agent outputs and an explicit `no_trade` decision are persisted to Supabase. Strategy candidates and their review stages are stored separately. At most one virtual candidate per symbol/strategy is followed to a sampled stop, TP1 or 45-minute horizon; tracking resumes after restart.

News and macro feeds are **not configured**. Their missing status causes a funding veto. Daily/weekly account performance, drawdown, stop risk and correlated exposures are not fully reconciled. The runtime therefore never funds a proposal or places an order.

The agents are deterministic research logic, not connected external AI services. Scores are heuristics, not calibrated probabilities. Tick volume is a proxy. Opening ranges use timezone-aware cash-opening templates without a holiday calendar. Virtual outcomes use sampled bid/ask quotes and omit actual fills, fees, slippage and intratick price paths; they are not broker returns or a backtest. Improvement recommendations never change rules automatically. Real trade management, replay/walk-forward validation, external feeds and dashboard timelines remain separate milestones.

## Windows setup and diagnostic

Run in PowerShell from `C:\Users\Jonas\TradingBot` on `feature/pepperstone-demo-bridge`. Stop an existing bridge with **Ctrl+C** before updating:

```powershell
git pull --ff-only
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\scripts\Setup-Windows.ps1
.\.venv\Scripts\python.exe .\services\mt5-engine\main.py --once
```

Setup checks Git and Python 3.12 x64, installs the pinned Windows dependencies including MT5 and timezone data, checks imports/dependency conflicts and runs the offline core/safety/integration tests. It does not start trading or change an existing `.env`.

Configure `.env` locally using `.env.example`: `SUPABASE_URL` is the project base URL, without `/rest/v1/`; `SUPABASE_SERVICE_ROLE_KEY` accepts the server-side secret key. MT5 must be logged in to the configured Pepperstone demo account. Never share or commit keys/passwords. Existing shell environment variables take precedence over `.env`.

`--once` collects one round, persists the nine agent outputs for each analyzed symbol and exits. It fails if there are persistence/analysis errors or no fresh quotes/analysis. Closed markets may have no fresh quotes; retry during the relevant trading session. Symbols with stale quotes are skipped and shown in the heartbeat count.

After a successful diagnostic, start continuous observation:

```powershell
.\.venv\Scripts\python.exe .\services\mt5-engine\main.py
```

### Timestamp basis

The observed PepperstoneUK-Demo terminal returns tick timestamp values approximately three hours ahead of a verified Windows UTC clock in October. `MT5_TICK_TIME_MODE=pepperstone_server` is therefore the bridge default for this installation. The conversion follows Pepperstone's documented GMT+3 during US DST / GMT+2 otherwise, using New York timezone rules rather than a fixed subtraction or European DST. `MT5_TICK_TIME_MODE=utc` remains available for feeds whose values already represent UTC. Do not change modes simply to make stale quotes pass.

Bars are checked independently: `MT5_BAR_TIME_MODE=auto` selects between UTC and Pepperstone server-wall encoding only when exactly one conversion gives a latest returned bar age between zero and ten minutes. This check happens before filtering future/forming bars. It does not estimate arbitrary clock offsets. An indeterminate/stale history is rejected. Explicit `utc`/`pepperstone_server` bar modes are also available. DST-ambiguous/nonexistent server-wall labels fail closed.

Persisted timestamps are UTC; market telemetry records the original tick value and conversion mode in `technical_context`. Quotes still expire after the configured maximum age (60 seconds by default); only two seconds of future clock jitter are tolerated. This is not a bypass for an incorrect system clock. Existing `.env` files need no change to use the new defaults.

Expect `SHADOW ... 9 agents ... orders=0` lines on newly closed M5 bars and a heartbeat every minute. Candidate count may be zero when no setup qualifies. Use Ctrl+C to stop. `SHADOW_ANALYSIS_ENABLED=false` leaves quote telemetry only; neither setting enables orders.

## Database setup

For a fresh project, apply the core schema first, then `supabase/learning_schema.sql`, then `supabase/shadow_integration_schema.sql`. The latter adds evaluation identifiers and uniqueness constraints for retry-safe writes. Learning tables are server-only: RLS is enabled and privileges for `anon` and `authenticated` are revoked. The informational Supabase [RLS/no-policy notice](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy) is expected for these deliberately private tables; the server service role writes them.

## Source

- `services/agent_team/`: nine expert roles and governance.
- `services/decision-engine/`: Opening Range, Trend Pullback, Compression Breakout, Liquidity Sweep, committee, allocation and research components.
- `services/decision_engine/`: importable namespace for that existing source directory.
- `services/mt5-engine/market_features.py`: closed-bar validation and feature adapter.
- `services/mt5-engine/shadow_runtime.py`: persistence and sampled virtual tracking.
- `docs/EXPERT_TEAM.md`: governance model.

## Validation and promotion

Offline tests cover demo account safety, vetoes, all four strategies in both directions, closed-bar/stale-data guards, timezone changes, retry-safe persistence, restart recovery, sampled exits and a complete simulated MT5-to-storage cycle. Actual Windows/MT5 end-to-end validation requires running the diagnostic on the target machine.

Any future execution path requires separate implementation and explicit user approval. Promotion remains research/replay → shadow → approved demo validation → explicit live approval. No martingale, grid rescue, averaging down, stop widening or automatic strategy promotion.
