-- Add user attribution columns to ai_usage_logs
alter table if exists public.ai_usage_logs
    add column if not exists user_id uuid,
    add column if not exists user_email text;

create index if not exists ai_usage_logs_user_id_idx on public.ai_usage_logs (user_id);