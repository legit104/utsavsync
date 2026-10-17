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

## Run it

Two terminals, both left open:

```bash
hackathon_backend\start.bat
```

```bash
npm.cmd run dev
```

Then open http://localhost:5173 (API docs at http://localhost:8000/docs). On macOS/Linux, follow
the backend README and use `npm run dev`. Run `npm install` once after pulling new frontend packages.

## Online version

- **Website:** GitHub Pages, built by `.github/workflows/pages.yml` on every push to `main`
  (`https://legit104.github.io/utsavsync/`). Set repository variables `VITE_SUPABASE_URL`,
  `VITE_SUPABASE_ANON_KEY` (publishable key) and `VITE_API_URL` (the backend address below)
  under Settings → Secrets and variables → Actions → Variables.
- **Backend:** Render, from `render.yaml` (render.com → New → Blueprint → this repo). Enter
  `SUPABASE_URL`, `SUPABASE_ANON_KEY` and `SUPABASE_SERVICE_KEY` there when asked. The free
  plan sleeps when idle, so open the site a minute before demoing.

## Settings

| File | Contents |
|---|---|
| `.env` (repo root, copy `frontend.env.example`) | `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` (the **publishable** key only), `VITE_API_URL` |
| `hackathon_backend/.env` (copy `.env.example`) | `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (secret), `SUPABASE_ANON_KEY`, `AUTH_MODE=supabase`, `VOLUNTEER_SESSION_SECRET` |

Both `.env` files are git-ignored. Never commit them or share the secret key.

## Accounts and roles

Everyone needs an account: **Create account** on the login screen, then sign in. There is no
demo login, and without the Supabase settings nobody can sign in.

**Visitors** sign in with their account.

**Volunteers** cannot gain access by selecting the Volunteer tile or setting a browser header.
A coordinator issues an access code; the backend stores only its SHA-256 hash in
`volunteer_access_codes`, redeems it atomically in the database, and returns an eight-hour
signed pass. Picking "Volunteer" at sign-up never grants volunteer rights. Codes can be:

- **email-bound** (default): only that account can use it, once;
- **open** (`--any-email`): any signed-in account can use it, up to `--uses` times in total.
  Convenient for a team, but anyone holding the code can use it, so keep the expiry short.

1. Run `hackathon_backend/supabase_schema.sql` in the Supabase SQL editor (safe to re-run).
2. Set `VOLUNTEER_SESSION_SECRET` in `hackathon_backend/.env` to a random value, e.g.
   `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
3. Create a code from `hackathon_backend`:
   - `.venv\Scripts\python issue_volunteer_code.py volunteer@example.org --expires-hours 72`
   - `.venv\Scripts\python issue_volunteer_code.py --any-email --uses 5 --expires-hours 12`

   Share the printed code privately.
4. The volunteer selects **Volunteer**, signs in with their account and enters the code.

Volunteer-only actions are enforced by the API: field reports, sensor updates, site closures,
pickup completion, festival profile changes, simulation controls and the reroute demo.


Then open http://localhost:5173 (API docs at http://localhost:8000/docs). On macOS/Linux, follow
the backend README and use `npm run dev`. Run `npm install` once after pulling new frontend packages.

### Live updates between team devices

Run the backend and frontend on the team laptop, with both devices on the same trusted Wi-Fi:

1. On the team laptop, run `hackathon_backend/start-lan.bat` and `npm run dev:lan` in separate terminals.
2. Find the team laptop's IPv4 address with `ipconfig` (for example, `192.168.1.25`).
3. In the repo-root `.env`, set `VITE_API_URL=http://192.168.1.25:8000`, then restart Vite.
4. On both devices, open `http://192.168.1.25:5173` and sign in to the same festival engine.

The visitor dashboard checks site status every 2 seconds, so a volunteer closing or reopening a site
will appear automatically. The backend keeps live state in memory, so leave its terminal running;
restarting it resets the festival state. Use this only on a trusted network, and keep Supabase auth
configured for volunteer actions.