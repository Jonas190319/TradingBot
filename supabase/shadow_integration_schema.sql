-- Apply after learning_schema.sql. Server-only SHADOW outputs; never enables trading.
alter table public.agent_signals add column if not exists evaluation_id uuid references public.trade_decisions(id);
create unique index if not exists agent_signals_evaluation_agent_idx on public.agent_signals(evaluation_id, agent_type);
create unique index if not exists pretrade_events_candidate_stage_ts_idx on public.pretrade_events(candidate_id, stage, ts);
create unique index if not exists shadow_outcomes_candidate_idx on public.shadow_outcomes(candidate_id);
revoke all on public.pretrade_events, public.trade_management_events, public.shadow_outcomes from anon, authenticated;
grant select, insert, update on public.pretrade_events, public.trade_management_events, public.shadow_outcomes to service_role;
notify pgrst, 'reload schema';
