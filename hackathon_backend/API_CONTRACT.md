# UtsavSync API Contract (frontend ↔ backend)

Every endpoint below is **implemented and tested**. The examples are real responses from the
backend, trimmed where marked `…`. Interactive docs with "Try it out": **http://localhost:8000/docs**.

**Naming to match in the UI**

| UI wording | API value |
|---|---|
| Crowd status GREEN / ORANGE / RED | `"GREEN"` / `"AMBER"` / `"RED"` (plus `"CLOSED"`). Show AMBER in orange. |
| ALLOCATE / DIVERT / REJECT | `"ALLOCATED"` / `"DIVERTED"` / `"REJECTED"` (plus `"REROUTED"` for automatic moves) |
| Visitor / Volunteer | `"visitor"` / `"volunteer"` |

Times are `"HH:MM"` on the **simulated festival clock** (`sim_time`), not the real clock.
Fractions like `occupancy: 0.72` mean 72%.

---

## 1. Backend URL

Base URL: **`http://localhost:8000`**. Put it in the frontend's `.env`:

```bash
VITE_API_URL=http://localhost:8000
```

How to reach it from your laptop, best option first:

1. **Run the backend on your own laptop.** Clone `https://github.com/legit104/utsavsync`, then in
   `hackathon_backend/`: `python -m venv .venv`, `.venv\Scripts\activate`,
   `pip install -r requirements.txt`, `uvicorn app.main:app --reload`. Then `localhost:8000` just works.
2. **Use the backend on a teammate's laptop over the same Wi-Fi.** That laptop runs
   `uvicorn app.main:app --host 0.0.0.0 --port 8000` and shares its IP (from `ipconfig`), e.g.
   `VITE_API_URL=http://192.168.1.23:8000`. Windows Firewall must allow Python.

CORS is open to all origins in development, so Vite on 5173/5174 can call it directly.

## 2. Authentication

- **Supabase email/password**, done in the React app with `supabase-js` and the **anon key**.
- The frontend sends the Supabase access token on every request:
  `Authorization: Bearer <session.access_token>`.
- The backend checks the token with Supabase and reads the role from
  **`app_metadata.role`** (trusted, set by an admin), falling back to **`user_metadata.role`**.
  No role means `visitor`.
- **Right now `AUTH_MODE=off`**, so no login is needed while you integrate. To fake a user,
  send `X-User-Id: <any id>` (needed for `/my-groups`). When Supabase is set up we flip
  `AUTH_MODE=supabase` and the same frontend code keeps working.

Sign-up storing the role (frontend):

```js
await supabase.auth.signUp({
  email, password,
  options: { data: { role: "volunteer" } }   // or "visitor"
});
```

> For the demo it's fine for users to pick their role at sign-up. For a real launch, volunteers
> should be approved by setting `app_metadata.role` from the Supabase dashboard, because
> `user_metadata` can be edited by the user.

One fetch helper for the whole app:

```js
const API = import.meta.env.VITE_API_URL;

export async function api(path, { method = "GET", body } = {}) {
  const { data } = await supabase.auth.getSession();
  const res = await fetch(`${API}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(data.session && { Authorization: `Bearer ${data.session.access_token}` }),
    },
    body: body && JSON.stringify(body),
  });
  const json = await res.json();
  if (!res.ok) throw new Error(typeof json.detail === "string" ? json.detail : "Invalid input");
  return json;
}
```

**Who can call what**

| Who | Endpoints |
|---|---|
| Anyone (no login) | `GET /festivals`, `/status`, `/sites/{id}`, `/log`, `/swm/tasks`, `/swm/routes`, `/profile` |
| Signed-in visitor | `POST /requests`, `GET /my-groups`, `POST /reports` (counted as a citizen report) |
| Volunteer | All of the above + `POST /field-reports`, `/sensor`, `/sites/{id}/close`, `/sites/{id}/open`, `/swm/tasks/{id}/complete` |

`GET /me` returns who the backend thinks you are:

```json
{ "id": "visitor-123", "email": null, "role": "visitor", "auth": "off" }
```

All festival endpoints start with `/festivals/{festival_id}`, where `festival_id` is
`ganesh_utsav` or `navratri_garba`.

## 3. Visitor allocation

### `POST /festivals/{festival_id}/requests`

Request (only `group_size` is required; leave `preferred_site_id` empty to let the engine pick,
and `preferred_time` empty for "now"):

```json
{
  "group_name": "Patil family",
  "group_size": 25,
  "preferred_site_id": "chinchpokli_chintamani",
  "preferred_time": "19:00"
}
```

Response: **ALLOCATED**. Use `decision.decision`, `decision.assigned`, `decision.reason`, and
`decision.notifications.en/hi/mr` for the message shown to the visitor.

```json
{
  "decision": {
    "id": "LOG-0004",
    "type": "ALLOCATION",
    "sim_time": "18:00",
    "decision": "ALLOCATED",
    "request_id": "REQ-0002",
    "group": {
      "id": "GRP-0003", "name": "Patil family", "size": 25,
      "site_id": "chinchpokli_chintamani", "slot_time": "19:00",
      "status": "PENDING", "reroutes": 0, "requested_by": "visitor-123"
    },
    "requested": { "site_id": "chinchpokli_chintamani", "time": "19:00", "group_size": 25 },
    "assigned": {
      "site_id": "chinchpokli_chintamani",
      "site_name": "Chinchpoklicha Chintamani",
      "time": "19:00",
      "projected_occupancy": 0.508,
      "distance_km": 0.0
    },
    "reason": "Chinchpoklicha Chintamani stays GREEN at 51% of capacity after adding this group.",
    "actions": [
      { "audience": "VOLUNTEER", "action": "EXPECT_GROUP", "site_id": "chinchpokli_chintamani", "group_id": "GRP-0003", "group_size": 25, "time": "19:00" },
      { "audience": "CITIZEN", "action": "PROCEED_TO_SITE", "site_id": "chinchpokli_chintamani", "time": "19:00" }
    ],
    "notifications": {
      "en": "Your group Patil family is allocated to Chinchpoklicha Chintamani at 19:00.",
      "hi": "आपके समूह Patil family को 19:00 बजे Chinchpoklicha Chintamani आवंटित किया गया है।",
      "mr": "तुमच्या गट Patil family ला 19:00 वाजता Chinchpoklicha Chintamani येथे जागा देण्यात आली आहे."
    }
  },
  "triggered_events": []
}
```

**DIVERTED** (the preferred site would become AMBER, so the engine picked a nearby GREEN one).
Same shape; `assigned` is the new site and `requested` is what they asked for:

```json
{
  "decision": "DIVERTED",
  "requested": { "site_id": "lalbaugcha_raja", "time": "19:00", "group_size": 30 },
  "assigned": {
    "site_id": "ganesh_galli", "site_name": "Ganesh Galli (Mumbaicha Raja)",
    "time": "19:00", "projected_occupancy": 0.372, "distance_km": 0.33
  },
  "reason": "Lalbaugcha Raja would reach 73% of capacity (AMBER) at 19:00; Ganesh Galli (Mumbaicha Raja) at 19:00 (0.3 km away, 37% full) stays GREEN.",
  "notifications": { "en": "Lalbaugcha Raja is crowded. Please go to Ganesh Galli (Mumbaicha Raja) at 19:00 instead.", "hi": "…", "mr": "…" }
}
```

**REJECTED**: `group` and `assigned` are `null`.

```json
{
  "decision": "REJECTED",
  "group": null,
  "assigned": null,
  "reason": "Group of 120 is above the festival limit of 50 per group; please split into smaller groups.",
  "actions": [{ "audience": "CITIZEN", "action": "RETRY_LATER" }],
  "notifications": { "en": "Sorry, no safe slot is available for group College trip right now. Please try a later time.", "hi": "…", "mr": "…" }
}
```

### `GET /festivals/{festival_id}/my-groups`

The signed-in visitor's bookings. **Poll this on the visitor screen.** If a site turns RED,
the group's `site_id`/`slot_time` change and `latest_update` explains why. Show it as a
notification.

```json
[
  {
    "id": "GRP-0003",
    "name": "Patil family",
    "size": 25,
    "site_id": "ganesh_galli",
    "site_name": "Ganesh Galli (Mumbaicha Raja)",
    "site_status": "GREEN",
    "slot_time": "19:00",
    "status": "PENDING",
    "reroutes": 1,
    "latest_update": {
      "type": "REROUTE",
      "decision": "REROUTED",
      "sim_time": "18:00",
      "reason": "Chinchpoklicha Chintamani turned RED; Ganesh Galli (Mumbaicha Raja) at 19:00 (1.2 km away, 38% full).",
      "notifications": {
        "en": "Update: Chinchpoklicha Chintamani is now overcrowded. Your group Patil family has been moved to Ganesh Galli (Mumbaicha Raja) at 19:00.",
        "hi": "…", "mr": "…"
      }
    }
  }
]
```

Group `status`: `PENDING` (booked, not arrived) → `ARRIVED` → `LEFT`, or `CANCELLED`.

## 4. Operations dashboard

### `GET /festivals/{festival_id}/status`

Everything the dashboard needs in one call. **Poll every 3–5 seconds.** One site shown;
`sites` has all of them (7 for Ganesh Utsav, 6 for Navratri).

```json
{
  "festival_id": "ganesh_utsav",
  "festival_name": "Ganesh Utsav",
  "sim_time": "18:00",
  "day": { "start": "06:00", "end": "23:00", "slot_minutes": 60 },
  "thresholds": { "green_max": 0.6, "amber_max": 0.85 },
  "sites": [
    {
      "id": "lalbaugcha_raja",
      "name": "Lalbaugcha Raja",
      "lat": 18.994,
      "lng": 72.8335,
      "capacity": 5000,
      "crowd": 3600,
      "occupancy": 0.72,
      "status": "AMBER",
      "closed": false,
      "trend_people_per_hour": 0,
      "pending_current_slot": 0,
      "pending_next_slot": 0,
      "projected_next_slot_occupancy": 0.72,
      "facilities": ["first_aid", "police_booth", "drinking_water", "toilets", "queue_barricades"],
      "hours": { "open": "06:00", "close": "23:00" },
      "waste": {
        "current_kg": 0.0,
        "bin_capacity_kg": 1440.0,
        "fill": 0.0,
        "forecast_kg": 468.0,
        "forecast_fill": 0.325,
        "open_task_id": null
      }
    }
  ],
  "groups": { "PENDING": 2 },
  "open_swm_tasks": 1,
  "log_entries": 9
}
```

Field guide: `crowd` = estimated people now, `occupancy` = crowd ÷ capacity, `waste.fill` =
bins now, `waste.forecast_fill` = bins in an hour. `lat`/`lng` are ready for Leaflet markers.

### `GET /festivals/{festival_id}/log?limit=50&type=REROUTE&site_id=…`

The decision log for the activity feed, newest last. Every entry has `id`, `type`, `sim_time`,
`reason` and usually `actions`. `type` is one of `ALLOCATION`, `REROUTE`, `STATUS_CHANGE`,
`PREDICTIVE_WARNING`, `REPORT`, `SWM_TASK`, `SWM_TASK_COMPLETED`, `SITE_CLOSED`, `SITE_REOPENED`.

```json
{
  "id": "LOG-0012",
  "type": "REROUTE",
  "sim_time": "18:00",
  "decision": "REROUTED",
  "from_site_id": "chinchpokli_chintamani",
  "to_site_id": "ganesh_galli",
  "from_time": "19:00",
  "to_time": "19:00",
  "reason": "Chinchpoklicha Chintamani turned RED; Ganesh Galli (Mumbaicha Raja) at 19:00 (1.2 km away, 38% full).",
  "actions": [
    { "audience": "VOLUNTEER", "action": "REDIRECT_GROUP", "site_id": "chinchpokli_chintamani", "group_id": "GRP-0003", "to_site_id": "ganesh_galli" },
    { "audience": "VOLUNTEER", "action": "EXPECT_GROUP", "site_id": "ganesh_galli", "group_id": "GRP-0003", "group_size": 25, "time": "19:00" },
    { "audience": "CITIZEN", "action": "GO_TO_ALTERNATE_SITE", "site_id": "ganesh_galli", "time": "19:00" }
  ],
  "notifications": { "en": "…", "hi": "…", "mr": "…" }
}
```

## 5. Volunteer report

### `POST /festivals/{festival_id}/field-reports` (volunteer)

One form, one call. Send any mix of fields; at least one reading is required.
`crowd_level` is `LOW` / `MEDIUM` / `HIGH` / `CRITICAL`; `crowd_count` (a head count) overrides it.

```json
{
  "site_id": "chinchpokli_chintamani",
  "crowd_level": "CRITICAL",
  "waste_level_percent": 82,
  "entries": 120,
  "exits": 40,
  "remarks": "Queue spilling onto the main road"
}
```

Response: the updated site plus every event the report caused. Here it turned the site RED,
rerouted a booked group and raised an SWM task. Show `events[].reason` as toasts.

```json
{
  "site": { "id": "chinchpokli_chintamani", "status": "RED", "crowd": 2956, "occupancy": 0.985,
            "waste": { "fill": 0.656, "forecast_fill": 1.113, "open_task_id": "SWM-0014" }, "…": "same shape as /status sites" },
  "events": [
    { "type": "REPORT", "reason": "Crowd estimate 1580 -> 2956 (99%), report weight 0.8.", "…": "…" },
    { "type": "STATUS_CHANGE", "from_status": "GREEN", "to_status": "RED", "reason": "Chinchpoklicha Chintamani is at 99% of capacity (GREEN < 60%, RED > 85%).", "…": "…" },
    { "type": "REROUTE", "decision": "REROUTED", "reason": "Chinchpoklicha Chintamani turned RED; Ganesh Galli (Mumbaicha Raja) at 19:00 (1.2 km away, 38% full).", "…": "…" },
    { "type": "REPORT", "reason": "Bin estimate 0% -> 66%, report weight 0.8.", "…": "…" },
    { "type": "SWM_TASK", "task_id": "SWM-0014", "priority": "HIGH", "reason": "Bins at 66% now, forecast 111% within 60 min (pickup trigger 75%).", "…": "…" }
  ]
}
```

Reports are blended with the current estimate (volunteer weight 0.8, citizen 0.4), so one
report moves the number strongly but not blindly.

### `POST /festivals/{festival_id}/reports` (any signed-in user)

A quick citizen report, one kind at a time:

```json
{ "site_id": "lalbaugcha_raja", "reporter_type": "citizen", "kind": "crowd", "crowd_level": "HIGH" }
{ "site_id": "lalbaugcha_raja", "reporter_type": "citizen", "kind": "waste", "bin_fill_percent": 90 }
```

With login on, `reporter_type` is taken from the user's role, not the body.

## 6. Waste / SWM

### `GET /festivals/{festival_id}/swm/tasks?status=OPEN`

`status` is `OPEN` or `COMPLETED`. `priority` is `URGENT` (bins ≥ 90% now), `HIGH` (forecast
overflow) or `NORMAL`.

```json
[
  {
    "id": "SWM-0014",
    "site_id": "chinchpokli_chintamani",
    "site_name": "Chinchpoklicha Chintamani",
    "lat": 18.9862,
    "lng": 72.8298,
    "status": "OPEN",
    "priority": "HIGH",
    "created_at": "18:00",
    "current_fill": 0.656,
    "forecast_fill": 1.113,
    "forecast_window_minutes": 60,
    "expected_load_kg": 935.3,
    "waste_breakdown_kg": { "flowers_and_garlands": 359.7, "food_and_prasad": 359.7, "plastic": 215.8 },
    "reason": "Bins at 66% now, forecast 111% within 60 min (pickup trigger 75%)."
  }
]
```

The recommended action is the matching `SWM_TASK` entry in `/log`:
`{ "audience": "SWM_TEAM", "action": "PICKUP", "priority": "HIGH", "expected_load_kg": 935.3, … }`.

### `POST /festivals/{festival_id}/swm/tasks/{task_id}/complete` (volunteer)

Body optional: `{ "collected_kg": 400 }` (default: bins emptied). Returns the task with
`"status": "COMPLETED"`, `completed_at` and `collected_kg`.

### `GET /festivals/{festival_id}/swm/routes`

Nearby open pickups grouped into one collection route:

```json
[
  {
    "route_id": "ROUTE-1",
    "priority": "HIGH",
    "distance_km": 0.0,
    "expected_load_kg": 935.3,
    "stops": [
      { "task_id": "SWM-0014", "site_id": "chinchpokli_chintamani", "site_name": "Chinchpoklicha Chintamani", "lat": 18.9862, "lng": 72.8298, "priority": "HIGH" }
    ]
  }
]
```

## 7. Festival configuration

`GET /festivals` lists festivals. `GET /festivals/{festival_id}/profile` returns the full
profile (sites, capacities, bins, thresholds, rules). The files are in `hackathon_backend/profiles/`.

```json
[
  { "id": "ganesh_utsav", "name": "Ganesh Utsav", "sites": 7, "hours": { "start": "06:00", "end": "23:00", "slot_minutes": 60 }, "sim_time": "18:00", "description": "…" },
  { "id": "navratri_garba", "name": "Navratri Garba", "sites": 6, "hours": { "start": "18:00", "end": "23:30", "slot_minutes": 30 }, "sim_time": "18:00", "description": "…" }
]
```

| | Ganesh Utsav | Navratri Garba |
|---|---|---|
| Hours / slot | 06:00–23:00, 60 min | 18:00–23:30, 30 min |
| Max group size | 50 | 40 |
| Visit length | 45 min | 90 min |
| Reroute radius | 5 km | 6 km |
| GREEN / RED thresholds | < 60% / > 85% | < 60% / > 85% |

**Ganesh Utsav sites** (`site_id`: capacity): `lalbaugcha_raja` 5000 · `ganesh_galli` 2500 ·
`chinchpokli_chintamani` 3000 · `gsb_kings_circle` 3000 · `khetwadi_ganraj` 2000 ·
`girgaon_chowpatty` 8000 (opens 10:00) · `andhericha_raja` 3000

**Navratri Garba sites**: `borivali_korakendra` 6000 · `kandivali_thakur_village` 4000 ·
`malad_garba_ground` 3500 · `goregaon_nesco` 7000 · `ghatkopar_garba` 3000 · `mulund_kalidas` 2500

A third festival can be added live with `POST /festivals` and the JSON in
`examples/dahi_handi.json`. The UI should read festivals from `GET /festivals` rather than
hard-coding two.

## 8. Demo controls (for the pitch screen)

These drive the simulated festival day. They need no login.

| Call | Body | What it does |
|---|---|---|
| `POST /festivals/{id}/simulate` | `{ "events": 75, "seed": 42, "replace_live": true }` | Plays a full festival day and makes it the live state, so the dashboard fills with real-looking data |
| `POST /festivals/{id}/clock/advance` | `{ "minutes": 30 }` | Moves time: groups arrive and leave, bins fill |
| `POST /festivals/{id}/demo/reroute` | none (optional `?site_id=`) | Books 3 groups, a volunteer reports CRITICAL, the site turns RED and all 3 are rerouted. Returns `reroutes[]` |
| `POST /festivals/{id}/what-if` | `{ "action": "close_site", "site_id": "lalbaugcha_raja", "at_time": "21:00" }` | Simulates on a copy and returns `summary` + `events`; the live state is unchanged. `action` can be `close_site`, `reopen_site` or `crowd_surge` (+ `extra_people`) |
| `POST /festivals/{id}/sites/{site_id}/close` · `/open` | `{ "reason": "…" }` | Officer closes or reopens a site (reroutes everyone booked there) |
| `POST /festivals/{id}/reset` | none | Starts the day over |

**Tip:** the live engine starts empty at opening time. Call `/simulate` with
`"replace_live": true` once when the dashboard loads in demo mode, so there is data to show.

## Errors

Errors always have a `detail` field. Show `detail` when it's a string.

| Code | Meaning | Example `detail` |
|---|---|---|
| 400 | Not allowed right now | `"Lalbaugcha Raja is already closed"` |
| 401 | Not signed in / token expired | `"Sign in required: send 'Authorization: Bearer <access token>'"` |
| 403 | Wrong role | `"Only volunteers can do this"` |
| 404 | Unknown festival, site or task | `"Unknown site 'nope' for festival 'ganesh_utsav'"` |
| 422 | Invalid body | `detail` is a list: `[{ "loc": ["body", "group_size"], "msg": "Input should be greater than 0" }]` |
