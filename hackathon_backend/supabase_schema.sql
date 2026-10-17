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

-- One-use volunteer passes. The API stores only SHA-256 hashes.
create table if not exists volunteer_access_codes (
  id          uuid primary key default gen_random_uuid(),
  email       text not null,
  code_hash   text not null unique,
  expires_at  timestamptz not null,
  redeemed_at timestamptz,
  redeemed_by text,
  created_at  timestamptz not null default now()
);
create index if not exists volunteer_access_codes_email on volunteer_access_codes (email, expires_at);
alter table volunteer_access_codes enable row level security;
