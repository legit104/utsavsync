# UtsavSync — Festival Operations Engine

Keeping Mumbai's festival crowds moving and its streets clean (PS 01, BMC Project Swachchha).

UtsavSync allocates visitor groups to festival sites and time slots, monitors crowd status
(GREEN / AMBER / RED), reroutes groups automatically when a site becomes unsafe, and raises
SWM pickup tasks before bins overflow. New festivals are added through configuration
profiles, not code.

| Folder | What it is |
|---|---|
| [`hackathon_backend/`](hackathon_backend/) | Python + FastAPI engine and REST API — see its [README](hackathon_backend/README.md) |
| `hackathon_frontend/` | React + Vite dashboard (coming soon) |

## Quick start (backend)

```bash
cd hackathon_backend
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open http://localhost:8000/docs.
