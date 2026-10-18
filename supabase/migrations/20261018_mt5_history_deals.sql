-- Run once in Supabase SQL editor. Private MT5 journal; no public read policies.
create table if not exists public.mt5_history_deals (
  account_server text not null,
  account_login bigint not null,
  ticket bigint not null,
  order_ticket bigint not null,
  position_id bigint not null,
  time_utc timestamptz not null,
  symbol text not null,
  deal_type integer not null,
  deal_entry integer not null,
  deal_reason integer not null,
  volume double precision not null,
  price double precision not null,
  profit double precision not null,
  commission double precision not null,
  swap double precision not null,
  fee double precision not null,
  magic bigint not null,
  comment text not null,
  imported_at timestamptz not null default now(),
  primary key (account_server, account_login, ticket)
);
create index if not exists mt5_history_deals_position_idx
  on public.mt5_history_deals (account_server, account_login, position_id, time_utc);
alter table public.mt5_history_deals enable row level security;
revoke all on public.mt5_history_deals from anon, authenticated;
-- service_role bypasses RLS; no public policies.
