-- Run once in the Supabase SQL editor. The backend writes with the service key,
-- so keep that key on the server only (never in the React app).

create table if not exists decision_log (
  id          text primary key,
  run_id      text not null,
  festival_id text not null,
  type        text not null,
  sim_time    text,
  payload     jsonb not null,
  created_at  timestamptz not null default now()
);
create index if not exists decision_log_festival_type on decision_log (festival_id, type);

create table if not exists swm_tasks (
  id          text primary key,
  run_id      text not null,
  festival_id text not null,
  site_id     text not null,
  status      text not null,
  priority    text not null,
  payload     jsonb not null,
  updated_at  timestamptz not null default now()
);
create index if not exists swm_tasks_open on swm_tasks (festival_id, status);

alter table decision_log enable row level security;
alter table swm_tasks enable row level security;
