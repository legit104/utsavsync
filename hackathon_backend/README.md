# Festival Operations Engine — Backend

Decision support layer between citizen/volunteer reports and BMC operations (PS 01).
It allocates groups to sites and time slots, tracks crowd status (GREEN / AMBER / RED),
reroutes groups automatically when a site turns RED, estimates waste and raises SWM pickup
tasks before bins overflow. Every decision is logged with a reason and machine-readable
JSON actions for BMC officers, SWM teams, volunteers and citizens.

**Stack:** Python + FastAPI, optional Supabase (PostgreSQL) for the decision log and SWM tasks.
Rule-based, no ML, free and open source only.

## Run it

**Windows shortcut:** double-click `start.bat` (or run `.\start.bat`). It creates the Python
environment and installs packages the first time, reinstalls only when `requirements.txt`
changes, and then starts the server.

Manual steps:

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open **http://localhost:8000/docs** for interactive API docs (every endpoint can be tried there).

```bash
pytest                                  # 16 tests: rules, reroute, SWM, simulation, API, login
python -m app.simulation --events 80    # simulate a full day for both festivals -> output/
```

### Supabase (optional)

The engine keeps live state in memory, so it works with no database. To also store every
decision and SWM task for officials:

1. Run `supabase_schema.sql` in the Supabase SQL editor.
2. Copy `.env.example` to `.env` and set `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`.

The service key stays on the backend only, never in the React app.

### Login and roles (optional)

`AUTH_MODE=off` (default) skips login so the frontend can integrate early. With
`AUTH_MODE=supabase` plus `SUPABASE_URL` and `SUPABASE_ANON_KEY`, the React app signs users in
with Supabase Auth and sends `Authorization: Bearer <access token>`. The backend reads the role
(`visitor` or `volunteer`) from `app_metadata.role`, falling back to `user_metadata.role`.

| Who | Can call |
|---|---|
| Anyone | Dashboard and read endpoints (`/status`, `/log`, `/swm/tasks`, …) |
| Signed-in visitor | `/requests`, `/my-groups`, `/reports` (weighted as a citizen) |
| Volunteer | Everything above plus `/field-reports`, `/sensor`, site close/open, completing SWM tasks |

## Architecture

```
React dashboard ──HTTP/JSON──▶ FastAPI (app/main.py)
                                   │
              ┌────────────────────┼─────────────────────┐
              ▼                    ▼                     ▼
     Festival profiles      FestivalEngine (one     Simulation / demo
     profiles/*.json        per festival, app/      (app/simulation.py)
     (app/profiles.py)      engine.py)
                                   │
                                   ▼
                     Decision log + SWM tasks ──▶ Supabase (optional, app/storage.py)
```

Workflow for every input: **Input → Data (site capacity, crowd, bins, profile) → Processing
(thresholds, arrivals, waste load) → Decision (Allocate / Divert / Reject, SWM task) → Output
(status + reason + JSON actions in the decision log).**

| File | What it does |
|---|---|
| `app/engine.py` | All rules: allocation, status, rerouting, predictive warnings, waste, SWM routes, what-if |
| `app/profiles.py` | Profile schema and validation |
| `app/simulation.py` | Festival day simulator and the scripted live reroute demo |
| `app/main.py` | REST API |
| `app/i18n.py` | Notifications in English, Hindi and Marathi |
| `app/storage.py` | Supabase writes (optional) |
| `profiles/` | Ganesh Utsav (7 sites) and Navratri Garba (6 sites) |
| `examples/dahi_handi.json` | Third profile to add live during judging |

## Rules and thresholds

All values below come from the festival profile, so they change by configuration, not code.

**Crowd status** — occupancy = people on site ÷ capacity

| Status | Occupancy (default) | Engine response |
|---|---|---|
| GREEN | below 60% (`green_max`) | Allocate |
| AMBER | 60–85% (`amber_max`) | Divert to a GREEN alternative if one exists, else allocate with caution (`allow_amber_allocation`) |
| RED | above 85% | Reject new groups; reroute pending groups; alert BMC officer |
| CLOSED | officer closed the site | Reroute **all** pending groups |

**Allocation** — each request is judged on *current crowd + groups already allocated to that
slot + the new group*. If the preferred site/slot would not stay GREEN, the engine searches
alternatives within `max_reroute_distance_km` and up to `max_slot_shift` slots later, ranked by
`distance + slot_shift_penalty_km × slots of delay` (a nearby site now beats the same site an
hour later). Groups above `max_group_size` or outside festival hours are rejected.

**Automatic rerouting** — when a site turns RED (or closes), every group that has not arrived
yet and is due within `reroute_window_minutes` is moved to the best alternative. If none exists
the group is cancelled with a reason and the BMC officer is asked to review.

**Predictive warning** — an AMBER site whose crowd is still growing (least-squares trend over
the last 30 minutes) plus groups due next slot is projected forward; if it would be RED by the
next slot, BMC and volunteers are warned before it happens.

**Reports** — volunteer reports carry weight 0.8, citizen reports 0.4: the new estimate is
`weight × reported + (1 − weight) × current`. Crowd levels map to LOW 30%, MEDIUM 65%,
HIGH 90%, CRITICAL 110% of capacity, or send an exact `crowd_count`.

**Waste** — bins fill at `crowd × Σ per_person_per_hour_kg`. Forecast = current waste +
(crowd + groups due within `forecast_minutes`) × rate. When current or forecast fill reaches
`pickup_trigger_fill` (75%) an SWM task is raised: **URGENT** if bins are already ≥ 90%,
**HIGH** if the forecast overflows, else NORMAL. Open tasks within `route_cluster_km` of each
other are grouped into one collection route.

## API overview

Frontend developers: see **[API_CONTRACT.md](API_CONTRACT.md)** for request/response JSON for
every endpoint, login, and naming.

All festival endpoints are under `/festivals/{festival_id}` (`ganesh_utsav`, `navratri_garba`).

| Method | Path | Purpose |
|---|---|---|
| GET | `/festivals` | List festivals |
| POST | `/festivals` | Add a festival live from a profile JSON |
| GET | `/{id}/status` | Dashboard: every site's status, crowd, bins, pending groups |
| POST | `/{id}/requests` | Group request → ALLOCATED / DIVERTED / REJECTED + reason |
| GET | `/me` | Signed-in user and role |
| GET | `/{id}/my-groups` | A visitor's bookings with their latest site, time and reroute message |
| POST | `/{id}/reports` | Citizen/volunteer crowd or waste report |
| POST | `/{id}/field-reports` | Volunteer form: crowd, bin level, entry/exit counts and remarks in one call |
| POST | `/{id}/sensor` | Simulated entry/exit counts |
| POST | `/{id}/clock/advance` | Move simulated time (groups arrive/leave, bins fill) |
| POST | `/{id}/sites/{site}/close` · `/open` | Officer closes/reopens a site |
| GET | `/{id}/swm/tasks` · `/swm/routes` | Pickup tasks and grouped routes |
| POST | `/{id}/swm/tasks/{task}/complete` | SWM team marks pickup done |
| GET | `/{id}/log` | Decision log (filter by `type`, `site_id`) |
| POST | `/{id}/what-if` | "What if Site X closes at 21:00?" on a copy of the engine |
| POST | `/{id}/demo/reroute` | Scripted live rerouting demo |
| POST | `/{id}/simulate` | Full day of 50–100 requests/reports (`replace_live: true` to show it on the dashboard) |
| POST | `/{id}/reset` | Restart the festival day |

Example decision:

```json
{
  "type": "ALLOCATION",
  "decision": "DIVERTED",
  "sim_time": "19:10",
  "reason": "Lalbaugcha Raja would reach 78% of capacity (AMBER) at 19:00; Ganesh Galli (Mumbaicha Raja) at 19:00 (0.3 km away, 41% full) stays GREEN.",
  "assigned": { "site_id": "ganesh_galli", "time": "19:00", "projected_occupancy": 0.41 },
  "actions": [
    { "audience": "VOLUNTEER", "action": "EXPECT_GROUP", "site_id": "ganesh_galli", "group_size": 30 },
    { "audience": "CITIZEN", "action": "GO_TO_ALTERNATE_SITE", "site_id": "ganesh_galli", "time": "19:00" }
  ],
  "notifications": { "en": "...", "hi": "...", "mr": "..." }
}
```

## 5-minute demo script

1. `POST /festivals/ganesh_utsav/simulate` with `{"replace_live": true}` — a full day; show the summary and dashboard.
2. `POST /festivals/ganesh_utsav/reset`, then `POST /clock/advance` `{"minutes": 240}`.
3. `POST /festivals/ganesh_utsav/demo/reroute` — groups booked at a site, a volunteer reports CRITICAL, the site turns RED and every booked group is rerouted with a reason and Hindi/Marathi messages.
4. `POST /what-if` `{"action": "close_site", "site_id": "lalbaugcha_raja", "at_time": "21:00"}` — impact with no change to live state.
5. `GET /swm/routes` — nearby pickups grouped into one route.
6. `POST /festivals` with `examples/dahi_handi.json` — a third festival goes live without code.

## Adding a festival

Copy a file in `profiles/`, change sites, timings, thresholds, bins, waste rates and rules, and
either drop it in `profiles/` (then `POST /festivals/reload`) or `POST` it to `/festivals`.
Festival hours must fall within one calendar day.
