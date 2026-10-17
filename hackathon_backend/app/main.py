"""HTTP API for the Festival Operations Engine.

Run:  uvicorn app.main:app --reload
Docs: http://localhost:8000/docs
"""

from __future__ import annotations

import os
import hashlib
import threading
from contextlib import contextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import httpx

from .auth import User, auth_enabled, current_user, issue_volunteer_token, require_volunteer
from .engine import FestivalEngine, NotFoundError, to_hhmm
from .models import (AdvanceClock, CompleteTask, FieldReport, GroupRequest, Report, SensorUpdate, SimulateRequest,
                     SiteAction, VolunteerAccessCode, WhatIf)
from .profiles import FestivalProfile, load_profiles, save_profile
from .simulation import run_reroute_demo, simulate_day
from .storage import storage_from_env

load_dotenv()

app = FastAPI(
    title="Festival Operations Engine",
    version="1.0.0",
    description="Decision support between citizen/volunteer reports and BMC operations: "
                "group allocation, crowd status, automatic rerouting and SWM pickup tasks, "
                "driven entirely by festival profiles.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)

storage = storage_from_env()
profiles: dict[str, dict] = {}
engines: dict[str, FestivalEngine] = {}
locks: dict[str, threading.Lock] = {}


def start_engine(profile: dict) -> FestivalEngine:
    profiles[profile["id"]] = profile
    locks.setdefault(profile["id"], threading.Lock())
    engines[profile["id"]] = FestivalEngine(profile, storage)
    return engines[profile["id"]]


for _profile in load_profiles().values():
    start_engine(_profile)


@contextmanager
def festival(festival_id: str):
    """Fetch a festival's engine, hold its lock, and turn engine errors into HTTP errors."""
    if festival_id not in engines:
        raise HTTPException(404, f"Unknown festival '{festival_id}'. See GET /festivals.")
    with locks[festival_id]:
        try:
            yield engines[festival_id]
        except NotFoundError as exc:
            raise HTTPException(404, exc.args[0]) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


def new_events(engine: FestivalEngine, since: int, exclude: dict | None = None) -> list[dict]:
    return [e for e in engine.log[since:] if e is not exclude]


# ------------------------------------------------------------------- meta

@app.get("/", tags=["meta"])
def root():
    return {"service": "Festival Operations Engine", "docs": "/docs", "festivals": list(engines),
            "database": "supabase" if storage else "in-memory",
            "auth": "supabase" if auth_enabled() else "off"}


@app.get("/health", tags=["meta"])
def health():
    return {"ok": True}


@app.get("/me", tags=["meta"])
def me(user: User = Depends(current_user)):
    """Who the backend thinks is calling, and their role (visitor or volunteer)."""
    return {"id": user.id, "email": user.email, "role": user.role, "auth": "supabase" if auth_enabled() else "off"}


@app.post("/volunteers/verify-code", tags=["auth"])
def verify_volunteer_code(body: VolunteerAccessCode):
    """Redeem a one-time email-bound code and issue a short-lived volunteer session."""
    if storage is None:
        raise HTTPException(503, "Volunteer verification needs Supabase database settings on the backend")
    if not os.getenv("VOLUNTEER_SESSION_SECRET"):
        raise HTTPException(503, "Volunteer sessions are not configured on this server")
    email = body.email.strip().lower()
    code_hash = hashlib.sha256(body.access_code.strip().encode("utf-8")).hexdigest()
    try:
        invite = storage.redeem_volunteer_code(email, code_hash)
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Could not verify the volunteer code in the database") from exc
    if invite is None:
        raise HTTPException(403, "This volunteer code is invalid, expired, already used, or assigned to another email")
    token, expires = issue_volunteer_token("volunteer:" + email, email)
    return {"access_token": token, "token_type": "bearer", "expires_at": expires,
            "user_id": "volunteer:" + email, "role": "volunteer"}

# --------------------------------------------------------------- profiles

@app.get("/festivals", tags=["profiles"])
def list_festivals():
    return [{"id": e.id, "name": e.name, "description": e.profile.get("description", ""),
             "sites": len(e.sites), "hours": e.profile["day"], "sim_time": to_hhmm(e.clock)}
            for e in engines.values()]


@app.post("/festivals", status_code=201, tags=["profiles"], dependencies=[Depends(require_volunteer)])
def add_festival(profile: FestivalProfile, overwrite: bool = False):
    """Add a festival live by uploading its profile. No code changes needed."""
    if profile.id in profiles and not overwrite:
        raise HTTPException(409, f"Festival '{profile.id}' already exists; pass ?overwrite=true to replace it.")
    data = profile.model_dump()
    save_profile(data)
    with locks.setdefault(profile.id, threading.Lock()):
        start_engine(data)
    return {"message": f"{profile.name} is live with {len(profile.sites)} sites.", "id": profile.id}


@app.post("/festivals/reload", tags=["profiles"], dependencies=[Depends(require_volunteer)])
def reload_festivals():
    """Re-read every JSON file in profiles/ and restart those festivals from scratch."""
    loaded = load_profiles()
    for profile in loaded.values():
        with locks.setdefault(profile["id"], threading.Lock()):
            start_engine(profile)
    return {"reloaded": list(loaded)}


@app.get("/festivals/{festival_id}/profile", tags=["profiles"])
def get_profile(festival_id: str):
    with festival(festival_id) as engine:
        return engine.profile


@app.post("/festivals/{festival_id}/reset", tags=["profiles"], dependencies=[Depends(require_volunteer)])
def reset_festival(festival_id: str):
    """Start the festival day over (clock back to opening time, no groups or tasks)."""
    with festival(festival_id) as engine:
        engines[festival_id] = FestivalEngine(engine.profile, storage)
        return engines[festival_id].snapshot()


# ------------------------------------------------------------- monitoring

@app.get("/festivals/{festival_id}/status", tags=["monitoring"])
def festival_status(festival_id: str):
    """Dashboard view: every site's crowd status, pending groups and bin levels."""
    with festival(festival_id) as engine:
        return engine.snapshot()


@app.get("/festivals/{festival_id}/sites/{site_id}", tags=["monitoring"])
def site_status(festival_id: str, site_id: str):
    with festival(festival_id) as engine:
        return engine.site_view(engine.site(site_id))


@app.get("/festivals/{festival_id}/groups", tags=["monitoring"])
def list_groups(festival_id: str, status: str | None = Query(None, examples=["PENDING"])):
    with festival(festival_id) as engine:
        return [g.to_dict() for g in engine.groups.values() if status is None or g.status == status.upper()]


@app.get("/festivals/{festival_id}/log", tags=["monitoring"])
def decision_log(festival_id: str, type: str | None = Query(None, examples=["REROUTE"]),
                 site_id: str | None = None, limit: int = Query(200, ge=1, le=5000)):
    """Every decision with its reason and JSON actions, newest last."""
    with festival(festival_id) as engine:
        entries = [e for e in engine.log
                   if (type is None or e["type"] == type.upper())
                   and (site_id is None or site_id in (e.get("site_id"), e.get("from_site_id"), e.get("to_site_id"),
                                                       (e.get("assigned") or {}).get("site_id")))]
        return entries[-limit:]


# ------------------------------------------------------------- allocation

@app.post("/festivals/{festival_id}/requests", tags=["allocation"])
def request_slot(festival_id: str, request: GroupRequest, user: User = Depends(current_user)):
    """Allocate a group to a site and time slot: ALLOCATED, DIVERTED or REJECTED, with a reason."""
    with festival(festival_id) as engine:
        start = len(engine.log)
        decision = engine.allocate({**request.model_dump(), "requested_by": user.id})
        return {"decision": decision, "triggered_events": new_events(engine, start, decision)}


@app.get("/festivals/{festival_id}/my-groups", tags=["allocation"])
def my_groups(festival_id: str, user: User = Depends(current_user)):
    """The signed-in visitor's bookings with their latest site and time (shows reroutes)."""
    if not user.id:
        raise HTTPException(401, "Sign in first (or send X-User-Id while AUTH_MODE=off)")
    with festival(festival_id) as engine:
        groups = [g for g in engine.groups.values() if g.requested_by == user.id]
        latest = {}
        for entry in engine.log:
            group_id = (entry.get("group") or {}).get("id")
            if group_id and entry.get("notifications"):
                latest[group_id] = entry
        return [{**g.to_dict(), "site_name": engine.sites[g.site_id].name,
                 "site_status": engine.sites[g.site_id].status,
                 "latest_update": {k: latest[g.id][k] for k in ("type", "decision", "sim_time", "reason", "notifications")}
                 if g.id in latest else None}
                for g in groups]


# ----------------------------------------------------------------- reports

@app.post("/festivals/{festival_id}/reports", tags=["reports"])
def submit_report(festival_id: str, report: Report, user: User = Depends(current_user)):
    """Citizen or volunteer crowd/waste report. May trigger status changes, reroutes and SWM tasks.

    With login on, reporter_type comes from the user's role, not the request body.
    """
    data = report.model_dump()
    if user.verified:
        data["reporter_type"] = user.reporter_type
    with festival(festival_id) as engine:
        start = len(engine.log)
        entry = engine.report(data)
        return {"report": entry, "site": engine.site_view(engine.site(report.site_id)),
                "triggered_events": new_events(engine, start, entry)}


@app.post("/festivals/{festival_id}/field-reports", tags=["reports"])
def submit_field_report(festival_id: str, report: FieldReport, user: User = Depends(require_volunteer)):
    """Volunteer form in one call: gate counts, crowd reading, bin level and remarks."""
    with festival(festival_id) as engine:
        site = engine.site(report.site_id)
        start = len(engine.log)
        base = {"site_id": site.id, "reporter_type": "volunteer", "note": report.remarks}
        if report.entries or report.exits:
            engine.sensor(site.id, report.entries, report.exits)
        if report.crowd_count is not None or report.crowd_level:
            engine.report({**base, "kind": "crowd", "crowd_level": report.crowd_level,
                           "crowd_count": report.crowd_count})
        if report.waste_level_percent is not None:
            engine.report({**base, "kind": "waste", "bin_fill_percent": report.waste_level_percent})
        return {"site": engine.site_view(site), "events": new_events(engine, start)}


@app.post("/festivals/{festival_id}/sensor", tags=["reports"], dependencies=[Depends(require_volunteer)])
def sensor_update(festival_id: str, update: SensorUpdate):
    """Simulated entry/exit gate counts."""
    with festival(festival_id) as engine:
        start = len(engine.log)
        site = engine.sensor(update.site_id, update.entries, update.exits)
        return {"site": site, "triggered_events": new_events(engine, start)}


# -------------------------------------------------------------- operations

@app.post("/festivals/{festival_id}/sites/{site_id}/close", tags=["operations"], dependencies=[Depends(require_volunteer)])
def close_site(festival_id: str, site_id: str, body: SiteAction = SiteAction()):
    """Close a site; every pending group there is rerouted automatically."""
    with festival(festival_id) as engine:
        start = len(engine.log)
        engine.close_site(site_id, body.reason)
        return {"events": new_events(engine, start), "site": engine.site_view(engine.site(site_id))}


@app.post("/festivals/{festival_id}/sites/{site_id}/open", tags=["operations"], dependencies=[Depends(require_volunteer)])
def open_site(festival_id: str, site_id: str, body: SiteAction = SiteAction()):
    with festival(festival_id) as engine:
        start = len(engine.log)
        engine.open_site(site_id, body.reason)
        return {"events": new_events(engine, start), "site": engine.site_view(engine.site(site_id))}


@app.get("/festivals/{festival_id}/swm/tasks", tags=["operations"])
def swm_tasks(festival_id: str, status: str | None = Query(None, examples=["OPEN"])):
    with festival(festival_id) as engine:
        return [t for t in engine.swm_tasks.values() if status is None or t["status"] == status.upper()]


@app.post("/festivals/{festival_id}/swm/tasks/{task_id}/complete", tags=["operations"],
          dependencies=[Depends(require_volunteer)])
def complete_swm_task(festival_id: str, task_id: str, body: CompleteTask = CompleteTask()):
    with festival(festival_id) as engine:
        return engine.complete_task(task_id, body.collected_kg)


@app.get("/festivals/{festival_id}/swm/routes", tags=["operations"])
def swm_routes(festival_id: str):
    """Open pickups grouped into collection routes by distance."""
    with festival(festival_id) as engine:
        return engine.swm_routes()


# -------------------------------------------------------------- simulation

@app.post("/festivals/{festival_id}/clock/advance", tags=["simulation"], dependencies=[Depends(require_volunteer)])
def advance_clock(festival_id: str, body: AdvanceClock):
    """Move simulated time forward: groups arrive and leave, bins fill."""
    with festival(festival_id) as engine:
        start = len(engine.log)
        engine.advance(body.minutes)
        return {"sim_time": to_hhmm(engine.clock), "events": new_events(engine, start), "status": engine.snapshot()}


@app.post("/festivals/{festival_id}/what-if", tags=["simulation"])
def what_if(festival_id: str, scenario: WhatIf):
    """E.g. "What happens if Lalbaugcha Raja closes at 21:00?" Runs on a copy; live state is untouched."""
    with festival(festival_id) as engine:
        return engine.what_if(scenario.model_dump())


@app.post("/festivals/{festival_id}/demo/reroute", tags=["simulation"], dependencies=[Depends(require_volunteer)])
def demo_reroute(festival_id: str, site_id: str | None = None):
    """Live demo: book groups at a site, then a volunteer reports a surge. Watch them get rerouted."""
    with festival(festival_id) as engine:
        return run_reroute_demo(engine, site_id)


@app.post("/festivals/{festival_id}/simulate", tags=["simulation"], dependencies=[Depends(require_volunteer)])
def simulate(festival_id: str, body: SimulateRequest = SimulateRequest()):
    """Simulate a full festival day of 50-100 requests and reports."""
    if festival_id not in profiles:
        raise HTTPException(404, f"Unknown festival '{festival_id}'. See GET /festivals.")
    engine, summary = simulate_day(profiles[festival_id], body.events, body.seed)
    if body.replace_live:
        with locks[festival_id]:
            engine.storage = storage
            engine.persist_all()
            engines[festival_id] = engine
    return {"summary": summary, "status": engine.snapshot(), "decision_log": engine.log}


