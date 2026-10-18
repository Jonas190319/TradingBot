create table if not exists public.mt5_research_signals (
 signal_id text primary key,
 account_server text not null,
 account_login bigint not null,
 symbol text not null,
 broker_symbol text not null,
 strategy text not null check (strategy in ('VWAP_RETEST','VALUE_AREA_REVERSAL','VALUE_AREA_BREAKOUT')),
 side text not null check (side in ('long','short')),
 bar_time_utc timestamptz not null,
 prior_day date not null,
 entry double precision not null,
 stop_loss double precision not null,
 take_profit double precision not null,
 vah double precision not null,
 poc double precision not null,
 val double precision not null,
 created_at timestamptz not null default now(),
 constraint research_signal_risk_direction check ((side='long' and stop_loss<entry and take_profit>entry) or (side='short' and stop_loss>entry and take_profit<entry))
);
create index if not exists mt5_research_signals_symbol_time on public.mt5_research_signals (symbol, bar_time_utc desc);
alter table public.mt5_research_signals enable row level security;
revoke all on public.mt5_research_signals from anon, authenticated;