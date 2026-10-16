-- UtsavSync database (PS 01: Festival Operations Engine)
--
-- Run once in the Supabase SQL editor. Safe to run again: it only creates what is missing.
--
-- Who writes what:
--   * The backend writes every table below with the secret (service role) key,
--     which bypasses row level security. Keep that key on the server only.
--   * The React app reads with the publishable (anon) key. The policies at the
--     bottom allow public reads of the dashboard tables and let signed-in users
--     read their own profile, bookings and alerts. Nobody writes from the browser.
--
-- Festival profiles stay config-driven: the JSON files in profiles/ are the
-- source of truth and are copied here on startup. A festival that exists only
-- in the festivals table (inserted from the dashboard) is loaded too, on
-- startup or POST /festivals/reload.


-- 1. User profiles: one row per Supabase Auth user, holding the app role.
--    Passwords live in Supabase Auth (auth.users), never in our tables.
create table if not exists profiles (
  id          uuid primary key references auth.users (id) on delete cascade,
  full_name   text,
  phone       text,
  role        text not null default 'visitor' check (role in ('visitor', 'volunteer')),
  created_at  timestamptz not null default now()
);

-- Create the profile automatically on sign-up, taking name/role from the
-- sign-up metadata: supabase.auth.signUp({ options: { data: { full_name, role } } })
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, full_name, phone, role)
  values (
    new.id,
    new.raw_user_meta_data ->> 'full_name',
    new.raw_user_meta_data ->> 'phone',
    case when new.raw_user_meta_data ->> 'role' = 'volunteer' then 'volunteer' else 'visitor' end
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();


-- 2. Festivals: the full profile (thresholds, rules, waste rates) as JSON.
create table if not exists festivals (
  id           text primary key,                -- e.g. 'ganesh_utsav'
  name         text not null,
  description  text,
  day_start    text not null,                   -- 'HH:MM'
  day_end      text not null,
  slot_minutes int  not null,
  profile      jsonb not null,                  -- the whole profile, as in profiles/*.json
  updated_at   timestamptz not null default now()
);


-- 3. Sites: the 5-8 locations of each festival, with capacity and bins.
create table if not exists sites (
  festival_id     text not null references festivals (id) on delete cascade,
  id              text not null,                -- e.g. 'lalbaugcha_raja'
  name            text not null,
  lat             double precision not null,
  lng             double precision not null,
  capacity        int  not null check (capacity > 0),
  open_time       text,                         -- 'HH:MM', null = festival start
  close_time      text,                         -- 'HH:MM', null = festival end
  facilities      text[] not null default '{}',
  bin_count       int  not null,
  bin_capacity_kg double precision not null,    -- per bin
  popularity      double precision not null default 1,
  primary key (festival_id, id)
);


-- 4. Live site status: crowd, GREEN/AMBER/RED and bin levels, one row per
--    site, updated after every change. The dashboard can read or subscribe to it.
create table if not exists site_status (
  festival_id      text not null,
  site_id          text not null,
  run_id           text not null,               -- which engine run wrote it
  sim_time         text not null,               -- festival clock 'HH:MM'
  status           text not null check (status in ('GREEN', 'AMBER', 'RED', 'CLOSED')),
  crowd            int  not null,
  occupancy        double precision not null,   -- crowd / capacity
  pending_next_slot int not null default 0,
  waste_kg         double precision not null,
  bin_fill         double precision not null,   -- 0.75 = 75% full
  forecast_fill    double precision not null,   -- expected fill in forecast window
  updated_at       timestamptz not null default now(),
  primary key (festival_id, site_id),
  foreign key (festival_id, site_id) references sites (festival_id, id) on delete cascade
);


-- 5. Groups: every visitor booking and where it currently stands
--    (changes when the engine reroutes it).
create table if not exists groups (
  id            text primary key,               -- '<run_id>-GRP-0003'
  run_id        text not null,
  festival_id   text not null,
  requested_by  text,                           -- Supabase user id of the visitor
  name          text not null,
  size          int  not null,
  site_id       text not null,
  slot_time     text not null,                  -- 'HH:MM'
  status        text not null check (status in ('PENDING', 'ARRIVED', 'LEFT', 'CANCELLED')),
  reroutes      int  not null default 0,
  payload       jsonb not null,
  updated_at    timestamptz not null default now()
);
create index if not exists groups_requested_by on groups (requested_by);


-- 6. Decision log: every allocation, reroute, status change, report,
--    predictive warning and SWM task, with its reason and JSON actions.
create table if not exists decision_log (
  id          text primary key,                 -- '<run_id>-LOG-0012'
  run_id      text not null,
  festival_id text not null,
  type        text not null,                    -- ALLOCATION, REROUTE, STATUS_CHANGE, REPORT, ...
  sim_time    text,
  payload     jsonb not null,
  created_at  timestamptz not null default now()
);
create index if not exists decision_log_festival_type on decision_log (festival_id, type);


-- 7. SWM pickup tasks for the waste teams.
create table if not exists swm_tasks (
  id          text primary key,                 -- '<run_id>-SWM-0014'
  run_id      text not null,
  festival_id text not null,
  site_id     text not null,
  status      text not null check (status in ('OPEN', 'COMPLETED')),
  priority    text not null check (priority in ('URGENT', 'HIGH', 'NORMAL')),
  payload     jsonb not null,
  updated_at  timestamptz not null default now()
);
create index if not exists swm_tasks_open on swm_tasks (festival_id, status);


-- 8. Notifications: messages for citizens, volunteers and SWM teams in
--    English, Hindi and Marathi (allocations, reroutes, pickup alerts).
create table if not exists notifications (
  id           text primary key,                -- same id as its decision_log entry
  run_id       text not null,
  festival_id  text not null,
  type         text not null,                   -- ALLOCATION, REROUTE, SWM_TASK
  user_id      text,                            -- visitor it is for, if any
  group_id     text,
  site_id      text,
  message_en   text not null,
  message_hi   text,
  message_mr   text,
  created_at   timestamptz not null default now()
);
create index if not exists notifications_user on notifications (user_id, created_at desc);


-- Row level security: on for every table. The backend's secret key bypasses it.
alter table profiles      enable row level security;
alter table festivals     enable row level security;
alter table sites         enable row level security;
alter table site_status   enable row level security;
alter table groups        enable row level security;
alter table decision_log  enable row level security;
alter table swm_tasks     enable row level security;
alter table notifications enable row level security;

-- Public dashboard data: anyone may read.
drop policy if exists "public read festivals"   on festivals;
drop policy if exists "public read sites"       on sites;
drop policy if exists "public read site_status" on site_status;
drop policy if exists "public read swm_tasks"   on swm_tasks;
create policy "public read festivals"   on festivals   for select using (true);
create policy "public read sites"       on sites       for select using (true);
create policy "public read site_status" on site_status for select using (true);
create policy "public read swm_tasks"   on swm_tasks   for select using (true);

-- Personal data: signed-in users read only their own rows.
drop policy if exists "read own profile"       on profiles;
drop policy if exists "read own groups"        on groups;
drop policy if exists "read own notifications" on notifications;
create policy "read own profile"       on profiles      for select using (auth.uid() = id);
create policy "read own groups"        on groups        for select using (auth.uid()::text = requested_by);
create policy "read own notifications" on notifications for select using (auth.uid()::text = user_id);
