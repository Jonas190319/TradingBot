-- Unified research-only journal for 13 shadow strategists and 3 profile strategies.
-- Keep the original mt5_research_signals table untouched for compatibility.
create table if not exists public.mt5_strategy_research_journal (
 signal_id text primary key,
 account_server text not null,
 account_login bigint not null,
 symbol text not null check (symbol in ('EURUSD','GBPUSD','USDJPY','XAUUSD','GER40','NAS100','US500','US30')),
 broker_symbol text not null,
 strategy text not null check (strategy in (
 'opening_range','trend_pullback','compression_breakout','liquidity_sweep',
 'supply_demand','range_trading','vwap_reclaim','mean_reversion',
 'harmonic_gartley','harmonic_bat','harmonic_butterfly','harmonic_crab','harmonic_shark',
 'VWAP_RETEST','VALUE_AREA_REVERSAL','VALUE_AREA_BREAKOUT'
 )),
 side text not null check (side in ('long','short')),
 bar_time_utc timestamptz not null,
 entry double precision not null,
 stop_loss double precision not null,
 take_profit double precision not null,
 source text not null check (source in ('shadow_strategist','profile_scanner')),
 setup_score double precision check (setup_score between 0 and 100),
 metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata)='object'),
 created_at timestamptz not null default now(),
 constraint strategy_journal_risk_direction check (
 (side='long' and stop_loss<entry and take_profit>entry)
 or (side='short' and stop_loss>entry and take_profit<entry)),
 constraint strategy_journal_source_match check (
 (source='profile_scanner' and strategy in ('VWAP_RETEST','VALUE_AREA_REVERSAL','VALUE_AREA_BREAKOUT'))
 or (source='shadow_strategist' and strategy not in ('VWAP_RETEST','VALUE_AREA_REVERSAL','VALUE_AREA_BREAKOUT')))
);
create index if not exists mt5_strategy_research_journal_symbol_time
 on public.mt5_strategy_research_journal (symbol,bar_time_utc desc);
create index if not exists mt5_strategy_research_journal_strategy_time
 on public.mt5_strategy_research_journal (strategy,bar_time_utc desc);
alter table public.mt5_strategy_research_journal enable row level security;
revoke all on public.mt5_strategy_research_journal from anon, authenticated;
