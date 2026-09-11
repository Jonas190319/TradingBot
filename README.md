# Trading Bot Starter

Initial scaffold for the Trive/MetaTrader 5 trading system.

## Architecture
- **Vercel / Next.js dashboard**: monitoring and control surface
- **Supabase**: accounts, strategies, signals, decisions, trades, metrics, improvement reports
- **Windows VPS / Python**: MetaTrader 5 bridge, market data and execution
- **GitHub**: source control and deployments

## Safety model
- Global trading mode starts at `OFF`.
- Live execution is separately gated by `live_execution_enabled=false`.
- `NO_TRADE` is a first-class decision.
- No martingale and no grid rescue.
- Candidate strategy changes go Shadow -> Demo -> explicit approval -> Live.

## Initial instruments
EURUSD, GBPUSD, USDJPY, XAUUSD, DAX40, NAS100.

## First milestone
1. Connect Trive MT5 Demo on a Windows machine/VPS.
2. Stream account state and market ticks into Supabase.
3. Run deterministic regime + risk checks.
4. Log all decisions, including rejected trades.
5. Build dashboard overview.

## Environment variables
Copy `.env.example` to the relevant service environment. Never commit real broker credentials or service-role keys.
