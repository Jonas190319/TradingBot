# Current Supabase schema

Project: `Trading Bot`

Core tables already created remotely:
- trading_accounts
- strategies
- strategy_versions
- market_context
- agent_signals
- trade_decisions
- trades
- performance_snapshots
- improvement_reports
- improvement_recommendations
- system_settings

All tables have RLS enabled. Authenticated users currently have read-only policies; server-side service role is intended for controlled writes.
