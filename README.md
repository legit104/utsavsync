# UtsavSync — Festival Operations Engine

Keeping Mumbai's festival crowds moving and its streets clean (PS 01, BMC Project Swachchha).

UtsavSync allocates visitor groups to festival sites and time slots, monitors crowd status
(GREEN / AMBER / RED), reroutes groups automatically when a site becomes unsafe, and raises
SWM pickup tasks before bins overflow. New festivals are added through configuration
profiles, not code.

| Part | Where | Stack |
|---|---|---|
| Frontend | repo root (`src/`, `public/`, `index.html`) | React + Vite |
| Backend | [`hackathon_backend/`](hackathon_backend/) — see its [README](hackathon_backend/README.md) and [API contract](hackathon_backend/API_CONTRACT.md) | Python + FastAPI |
| Database & login | Supabase (PostgreSQL + Auth) | |

## Run the backend

**Windows:** double-click `hackathon_backend/start.bat`, or run `.\start.bat` inside
`hackathon_backend`. The first run sets everything up; after that it starts in a few seconds.
Then open http://localhost:8000/docs.

**Manual / macOS / Linux:**

```bash
cd hackathon_backend
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Run the frontend

From the repo root, with Node.js installed:

```bash
npm install
npm run dev
```

Then open the URL Vite prints (usually http://localhost:5173). The frontend talks to the
backend at `http://localhost:8000`, so start the backend too.

## Secrets

Supabase keys go in `.env` files, which git ignores. Never commit them. The frontend only
ever gets the **publishable (anon)** key; the **secret (service role)** key stays in
`hackathon_backend/.env`.
