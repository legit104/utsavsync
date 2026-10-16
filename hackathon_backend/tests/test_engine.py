import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.engine import RED, FestivalEngine, to_hhmm
from app.profiles import FestivalProfile, load_profiles
from app.simulation import run_reroute_demo, simulate_day

PROFILES = load_profiles()
LALBAUG = "lalbaugcha_raja"


def ganesh() -> FestivalEngine:
    return FestivalEngine(PROFILES["ganesh_utsav"])


def test_at_least_two_festival_profiles():
    assert {"ganesh_utsav", "navratri_garba"} <= set(PROFILES)
    for profile in PROFILES.values():
        assert 5 <= len(profile["sites"]) <= 8


def test_allocates_when_site_stays_green():
    decision = ganesh().allocate({"group_size": 20, "preferred_site_id": LALBAUG})
    assert decision["decision"] == "ALLOCATED"
    assert decision["assigned"]["site_id"] == LALBAUG
    assert decision["actions"] and set(decision["notifications"]) == {"en", "hi", "mr"}


def test_rejects_group_above_limit():
    decision = ganesh().allocate({"group_size": 500, "preferred_site_id": LALBAUG})
    assert decision["decision"] == "REJECTED"
    assert "limit" in decision["reason"]


def test_diverts_when_preferred_site_is_busy():
    engine = ganesh()
    engine.sites[LALBAUG].crowd = int(engine.sites[LALBAUG].capacity * 0.7)
    engine._refresh()
    decision = engine.allocate({"group_size": 30, "preferred_site_id": LALBAUG})
    assert decision["decision"] == "DIVERTED"
    assert decision["assigned"]["site_id"] != LALBAUG
    assert decision["assigned"]["distance_km"] <= engine.rules["max_reroute_distance_km"]


def test_red_status_reroutes_pending_groups():
    engine = ganesh()
    next_slot = to_hhmm(engine.clock + engine.slot)
    booked = engine.allocate({"group_size": 25, "preferred_site_id": LALBAUG, "preferred_time": next_slot})
    assert booked["decision"] == "ALLOCATED"

    engine.report({"site_id": LALBAUG, "reporter_type": "volunteer", "kind": "crowd", "crowd_level": "CRITICAL"})

    assert engine.sites[LALBAUG].status == RED
    assert engine.groups[booked["group"]["id"]].site_id != LALBAUG
    assert any(e["type"] == "REROUTE" and e["decision"] == "REROUTED" for e in engine.log)


def test_reroute_demo_moves_every_booked_group():
    result = run_reroute_demo(ganesh())
    assert result["status_after"] == RED
    assert len(result["reroutes"]) == 3


def test_swm_task_raised_before_bins_overflow():
    engine = ganesh()
    engine.report({"site_id": LALBAUG, "reporter_type": "volunteer", "kind": "waste", "bin_fill_percent": 100})
    tasks = [t for t in engine.swm_tasks.values() if t["site_id"] == LALBAUG]
    assert len(tasks) == 1 and tasks[0]["status"] == "OPEN"
    engine.complete_task(tasks[0]["id"])
    assert engine.sites[LALBAUG].waste_kg == 0


def test_closing_a_site_reroutes_all_its_pending_groups():
    engine = ganesh()
    late = to_hhmm(engine.day_end - engine.slot)
    booked = engine.allocate({"group_size": 10, "preferred_site_id": "ganesh_galli", "preferred_time": late})
    engine.close_site("ganesh_galli")
    assert engine.groups[booked["group"]["id"]].site_id != "ganesh_galli"


def test_predictive_warning_before_site_turns_red():
    engine = ganesh()
    site = engine.sites[LALBAUG]
    for _ in range(12):  # crowd climbs 8% of capacity every 5 minutes
        engine.sensor(LALBAUG, entries=site.capacity * 8 // 100)
        engine.advance(5)
        if site.status == RED:
            break
    warnings = [e for e in engine.log if e["type"] == "PREDICTIVE_WARNING" and e["site_id"] == LALBAUG]
    first_red = next(e for e in engine.log if e["type"] == "STATUS_CHANGE" and e["to_status"] == RED)
    assert warnings and warnings[0]["id"] < first_red["id"]


def test_what_if_leaves_live_engine_untouched():
    engine = ganesh()
    engine.allocate({"group_size": 25, "preferred_site_id": LALBAUG, "preferred_time": to_hhmm(engine.clock + 60)})
    log_size = len(engine.log)
    result = engine.what_if({"action": "close_site", "site_id": LALBAUG})
    assert result["summary"].get("REROUTED") == 1
    assert len(engine.log) == log_size and not engine.sites[LALBAUG].closed


@pytest.mark.parametrize("festival_id", ["ganesh_utsav", "navratri_garba"])
def test_full_festival_day_simulation(festival_id):
    engine, summary = simulate_day(PROFILES[festival_id], events=80, seed=7)
    assert summary["total_inputs"] == 80
    assert sum(summary["allocation_decisions"].values()) >= 30
    assert summary["reroutes"]["rerouted"] >= 1
    assert summary["swm_tasks_created"] >= 1


def test_third_festival_profile_is_valid():
    path = Path(__file__).resolve().parent.parent / "examples" / "dahi_handi.json"
    profile = FestivalProfile.model_validate(json.loads(path.read_text(encoding="utf-8"))).model_dump()
    _, summary = simulate_day(profile, events=60)
    assert summary["total_inputs"] == 60


def test_api_round_trip():
    from app.main import app

    client = TestClient(app)
    assert client.post("/festivals/ganesh_utsav/reset").status_code == 200
    response = client.post("/festivals/ganesh_utsav/requests",
                           json={"group_size": 12, "preferred_site_id": LALBAUG})
    assert response.status_code == 200
    assert response.json()["decision"]["decision"] == "ALLOCATED"
    assert client.post("/festivals/ganesh_utsav/requests", json={"group_size": 12, "preferred_site_id": "nope"}).status_code == 404
    status = client.get("/festivals/ganesh_utsav/status").json()
    assert len(status["sites"]) == 7
    assert client.get("/festivals/unknown/status").status_code == 404


def test_visitor_sees_own_booking_after_reroute():
    from app.main import app

    client = TestClient(app)
    client.post("/festivals/ganesh_utsav/reset")
    me = {"X-User-Id": "visitor-1"}
    booked = client.post("/festivals/ganesh_utsav/requests", headers=me, json={
        "group_size": 12, "preferred_site_id": LALBAUG, "preferred_time": "07:00"}).json()["decision"]
    assert booked["decision"] == "ALLOCATED"

    result = client.post("/festivals/ganesh_utsav/field-reports", json={
        "site_id": LALBAUG, "crowd_level": "CRITICAL", "waste_level_percent": 80,
        "entries": 100, "remarks": "Gate 2 jammed"}).json()
    assert result["site"]["status"] == RED
    assert {e["type"] for e in result["events"]} >= {"REPORT", "REROUTE", "SWM_TASK"}

    mine = client.get("/festivals/ganesh_utsav/my-groups", headers=me).json()
    assert len(mine) == 1 and mine[0]["site_id"] != LALBAUG
    assert mine[0]["latest_update"]["decision"] == "REROUTED"
    assert client.get("/festivals/ganesh_utsav/my-groups", headers={"X-User-Id": "someone-else"}).json() == []


def test_supabase_login_and_roles(monkeypatch):
    from app import auth
    from app.main import app

    monkeypatch.setenv("AUTH_MODE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    users = {"visitor-token": {"id": "u1", "email": "v@x.in", "user_metadata": {"role": "visitor"}},
             "volunteer-token": {"id": "u2", "email": "vol@x.in", "app_metadata": {"role": "volunteer"}}}

    class FakeResponse:
        def __init__(self, token):
            self.status_code = 200 if token in users else 401
            self._data = users.get(token)

        def json(self):
            return self._data

    monkeypatch.setattr(auth.httpx, "get", lambda url, headers, timeout: FakeResponse(headers["Authorization"][7:]))
    auth._cache.clear()
    client = TestClient(app)
    report = {"site_id": LALBAUG, "crowd_level": "HIGH"}

    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer bad"}).status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer volunteer-token"}).json()["role"] == "volunteer"
    assert client.post("/festivals/ganesh_utsav/field-reports", json=report,
                       headers={"Authorization": "Bearer visitor-token"}).status_code == 403
    assert client.post("/festivals/ganesh_utsav/field-reports", json=report,
                       headers={"Authorization": "Bearer volunteer-token"}).status_code == 200
    # A visitor claiming to be a volunteer is still weighted as a citizen.
    sent = client.post("/festivals/ganesh_utsav/reports", headers={"Authorization": "Bearer visitor-token"},
                       json={**report, "reporter_type": "volunteer", "kind": "crowd"}).json()
    assert sent["report"]["reporter_type"] == "citizen"
    assert client.get("/festivals/ganesh_utsav/status").status_code == 200  # dashboard stays public
