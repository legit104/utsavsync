# UtsavSync — Festival Operations Engine

Keeping Mumbai's festival crowds moving and its streets clean (PS 01, BMC Project Swachchha).

UtsavSync allocates visitor groups to festival sites and time slots, monitors crowd status
(GREEN / AMBER / RED), reroutes groups automatically when a site becomes unsafe, and raises
SWM pickup tasks before bins overflow. New festivals are added through configuration
profiles, not code. The whole interface is available in English, Hindi and Marathi.

| Part | Where | Stack |
|---|---|---|
| Frontend | repo root (`src/`, `public/`, `index.html`) | React + Vite, Leaflet + OpenStreetMap |
| Backend | [`hackathon_backend/`](hackathon_backend/) — see its [README](hackathon_backend/README.md) and [API contract](hackathon_backend/API_CONTRACT.md) | Python + FastAPI |
| Database & login | Supabase (PostgreSQL + Auth) | |

## 1. First-time setup (once per laptop)

You need **Git**, **Python 3.11+** (tick "Add python.exe to PATH") and **Node.js**.

```bash
git clone https://github.com/legit104/utsavsync.git
cd utsavsync
npm.cmd install
```

Then create the two settings files (both are git-ignored; get the values from a teammate privately):

| File | Copy from | Contents |
|---|---|---|
| `.env` (repo root) | `frontend.env.example` | `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` (the **publishable** key only), `VITE_API_URL=http://localhost:8000` |
| `hackathon_backend/.env` | `hackathon_backend/.env.example` | `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (**secret** — never share or commit), `SUPABASE_ANON_KEY`, `AUTH_MODE=supabase`, `VOLUNTEER_SESSION_SECRET` (any long random text) |

The backend sets up its own Python environment the first time it starts (about a minute).

> **Windows PowerShell:** type `npm.cmd`, not `npm` — PowerShell blocks `npm`'s script wrapper.

## 2. Run it

Use **two terminals**, run one command in each, and leave both open while you use the site.

### On this laptop only

```bash
hackathon_backend\start.bat
```

```bash
npm.cmd run dev
```

Open **http://localhost:5173**. API docs: http://localhost:8000/docs.

### Shared with other laptops on the same Wi-Fi

Run these on **one** laptop (the "team laptop") instead:

```bash
hackathon_backend\start-lan.bat
```

```bash
npm.cmd run dev:lan
```

The backend window prints the team laptop's address (e.g. `192.168.1.25`). Everyone — including
the team laptop — opens **`http://THAT-ADDRESS:5173`**. Other laptops need nothing installed and
no `.env` changes; the site finds the backend on the team laptop by itself.

- If Windows asks whether Python or Node may use the network, allow **Private networks** only.
- College and public Wi-Fi often block laptops from reaching each other; a **phone hotspot**
  usually works. Use Wi-Fi sharing only on a trusted network.
- The address can change when you join a different Wi-Fi — check the backend window each time.

**Everyone sees the same live view.** Every open screen refreshes every 2 seconds (paused while
the tab is hidden): site colours, the map, pickups, routes, the decision log and My Groups. A
change made on one laptop shows up on the others within about 2 seconds.

## 3. Accounts and volunteer codes

Everyone needs an account: click **Create account** on the login screen, then sign in.

- **Email confirmation is off**, so new accounts can sign in immediately. If you turn it on
  (Supabase → Authentication → Sign In / Providers → User Signups → Confirm email), set up
  custom SMTP first: Supabase's built-in email only reaches members of your Supabase team and
  sends about 2 emails an hour. Accounts created while confirmation was on stay unconfirmed;
  confirm them under Authentication → Users, or delete them so the person can sign up again.
- **Visitors** just sign in.
- **Volunteers** also need an **access code**. Picking "Volunteer" at sign-up is not enough.

**Creating a volunteer code** (in a terminal that isn't running a server):

```bash
cd hackathon_backend
```

One code for the whole team — any account, up to 5 uses, valid 12 hours:

```bash
.venv\Scripts\python issue_volunteer_code.py --any-email --uses 5 --expires-hours 12
```

Or a code for one person — that email only, one use:

```bash
.venv\Scripts\python issue_volunteer_code.py their-email@example.com
```

Copy the printed code (it is shown only once) and share it privately. The volunteer chooses
**Volunteer**, signs in, pastes the code and clicks **Verify code & continue**. The volunteer
pass lasts 8 hours; after that they need a new code. The database stores only a hash of each
code, and volunteer-only actions (field reports, site closures, pickups, festival profiles,
simulation and demo controls) are enforced by the API.

## 4. The live festival day

- The festival opens **mid-day with realistic crowds** (Ganesh Utsav at 19:00, Navratri at
  21:15), so sites already show a mix of GREEN, AMBER and RED and some pickups are open. The
  time is set by `simulation.live_start` in each profile.
- **Progress is saved** to `hackathon_backend/state/` after every change. Restarting the
  backend — including the automatic restart when backend code is edited — carries on where
  it left off. Frontend edits update every open screen straight away.
- **Start over** with **Reset festival day** on the volunteer Operations screen (or stop the
  backend and delete `hackathon_backend/state/`). Editing a festival's profile file also starts
  that festival on a fresh day.

## 5. Online version (optional)

So people can use it from anywhere, without the team laptop:

- **Backend on Render:** render.com → New → **Blueprint** → this repo (it reads `render.yaml`).
  Enter `SUPABASE_URL`, `SUPABASE_ANON_KEY` and `SUPABASE_SERVICE_KEY` when asked. The free
  plan sleeps when idle — open the site a minute before demoing.
- **Website on GitHub Pages:** Settings → Pages → Source: **GitHub Actions** (private repos need
  GitHub Pro or the Student Developer Pack). Add repository variables `VITE_SUPABASE_URL`,
  `VITE_SUPABASE_ANON_KEY` (publishable key) and `VITE_API_URL` (the Render address) under
  Settings → Secrets and variables → Actions → Variables, then run the "Deploy UtsavSync to
  GitHub Pages" workflow. The site is at `https://legit104.github.io/utsavsync/`.
- In Supabase → Authentication → URL Configuration, add the site's address to Redirect URLs.

## Database

Run `hackathon_backend/supabase_schema.sql` once in the Supabase SQL editor (safe to re-run after
pulling changes to it). See the [backend README](hackathon_backend/README.md) for the tables.

## Troubleshooting

| Problem | Fix |
|---|---|
| `npm` "cannot be loaded because running scripts is disabled" | Use `npm.cmd` |
| Page says "DEMO MODE" / "Backend is offline" | The backend terminal isn't running — start it |
| "Unable to connect" in the browser | One of the two terminals was closed — start both again |
| Other laptop can't open the site | Use `start-lan.bat` + `npm.cmd run dev:lan`, the address from the backend window, and the same Wi-Fi; allow the firewall prompt |
| "Wrong email or password" | Create an account first, or check the password |
| "Please confirm your email first" | See *Accounts* above — confirm the user in Supabase |
| Volunteer code rejected | Codes are one-use (or `--uses` times), expire, and email-bound codes only work for that email — create a new one |
| `start.bat` fails on Python 3.15+ | Install Python 3.13 alongside, delete `hackathon_backend\.venv`, run `start.bat` again |
