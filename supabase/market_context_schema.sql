create table if not exists public.market_context (
 id uuid primary key default gen_random_uuid(),
 ts timestamptz not null,
 symbol text not null,
 bid double precision not null check (bid > 0),
 ask double precision not null check (ask >= bid),
 spread_points double precision,
 regime text not null default 'unknown',
 source text not null,
 created_at timestamptz not null default now()
);
create index if not exists market_context_symbol_ts_idx on public.market_context(symbol, ts desc);
alter table public.market_context enable row level security;
revoke all on public.market_context from anon, authenticated;
grant select, insert on public.market_context to service_role;
