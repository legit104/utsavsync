# UtsavSync

Festival operations prototype for safer crowd movement and cleaner festival sites. The interface uses the supplied UtsavSync login artwork and includes Visitor and Volunteer account selection, live site monitoring, a site map, group allocation, volunteer field reports, SWM tasks and grouped routes, what-if scenarios, day simulation, a decision log, and JSON festival profile management. The included Dahi Handi profile can be added as a third festival.

## Run locally

1. Install frontend dependencies with `npm install`.
2. Copy `.env.example` to `.env`.
3. Start the API from `hackathon_backend` using `start.bat` on Windows, or follow [the backend README](hackathon_backend/README.md).
4. Start the frontend with `npm run dev`.

The frontend uses `http://localhost:8000` by default. Set `VITE_API_URL` in `.env` to use another API host. When the API is unavailable, the dashboard shows sample data and disables engine-backed actions.

## Supabase email/password accounts

Set `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` in the frontend `.env`. Configure the same project in the backend and set `AUTH_MODE=supabase`; see the backend README for the required environment variables and role behavior. Leave the Supabase values blank to use prototype demo access.

## Operations engine

The FastAPI backend includes configurable JSON profiles for Ganesh Utsav and Navratri Garba, rule-based capacity-aware allocation, automatic rerouting when a site turns RED or closes, crowd and waste reporting, SWM pickup tasks and collection routes, a decision log, a what-if simulator, and API documentation at `/docs`.
