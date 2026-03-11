-- Create user_activity_logs to track logins and AI calls
create table if not exists user_activity_logs (
    id bigserial primary key,
    event_type text not null,
    user_id uuid,
    user_email text,
    context text,
    metadata jsonb,
    created_at timestamptz default now()
);

alter table user_activity_logs enable row level security;

create policy "service role full access" on user_activity_logs
for all
to service_role
using (true)
with check (true);

-- Optional: allow authenticated users to insert their own events (comment out if not desired)
-- create policy if not exists "authenticated can insert activity" on user_activity_logs
-- for insert to authenticated using (true) with check (true);

-- Index for time filtering
create index if not exists idx_user_activity_logs_created_at on user_activity_logs (created_at desc);