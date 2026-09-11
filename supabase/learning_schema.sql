-- Decision/learning extension for TradingBot.
-- Apply through Supabase migration tooling after review.

create table if not exists public.pretrade_events (
  id uuid primary key default gen_random_uuid(),
  candidate_id text not null,
  ts timestamptz not null,
  symbol text not null,
  strategy text not null,
  stage text not null,
  score numeric,
  bid numeric,
  ask numeric,
  spread numeric,
  features jsonb not null default '{}'::jsonb,
  notes jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists pretrade_events_candidate_idx on public.pretrade_events(candidate_id, ts);
create index if not exists pretrade_events_symbol_strategy_idx on public.pretrade_events(symbol, strategy, ts desc);

create table if not exists public.trade_management_events (
  id uuid primary key default gen_random_uuid(),
  trade_id text not null,
  ts timestamptz not null,
  price numeric not null,
  r_multiple numeric,
  mfe_r numeric,
  mae_r numeric,
  action text not null,
  reason text,
  new_stop numeric,
  reduce_pct numeric,
  context jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists trade_management_events_trade_idx on public.trade_management_events(trade_id, ts);

create table if not exists public.shadow_outcomes (
  id uuid primary key default gen_random_uuid(),
  candidate_id text not null,
  strategy text not null,
  symbol text not null,
  regime text,
  session text,
  direction text,
  was_executed boolean not null default false,
  committee_score numeric,
  setup_score numeric,
  realized_r numeric,
  mfe_r numeric,
  mae_r numeric,
  metadata jsonb not null default '{}'::jsonb,
  completed_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists shadow_outcomes_slice_idx on public.shadow_outcomes(strategy, symbol, regime, session);

alter table public.pretrade_events enable row level security;
alter table public.trade_management_events enable row level security;
alter table public.shadow_outcomes enable row level security;

-- Browser/dashboard reads can be added with explicit authenticated policies.
-- Writes should remain server-side via service role. Never expose service role keys to the frontend.
