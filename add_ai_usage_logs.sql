-- Creates ai_usage_logs for tracking AI call costs
-- Run this in Supabase SQL editor (or psql) on your project database

create table if not exists public.ai_usage_logs (
    id bigserial primary key,
    model text,
    prompt_tokens integer,
    response_tokens integer,
    total_tokens integer,
    cost_usd numeric(12,6),
    context text,
    created_at timestamptz not null default now()
);

-- Helpful index for date filtering
create index if not exists ai_usage_logs_created_at_idx on public.ai_usage_logs (created_at desc);

-- Optional: allow RLS only if you need it; the admin page uses service role
-- alter table public.ai_usage_logs enable row level security;
-- create policy "Allow service role" on public.ai_usage_logs for all using (auth.role() = 'service_role');
