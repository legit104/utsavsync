"""Replays the exact requests the React frontend (src/VisitorDashboard.jsx, src/api.js) sends,
with the same headers and bodies, and checks every field the UI reads is present."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import auth, main
from conftest import volunteer_headers

FRONTEND_SRC = Path(__file__).resolve().parents[2] / "src"
F = "/festivals/ganesh_utsav"
DEMO = {"X-User-Id": "utsavsync-demo-user", "X-Role": "visitor"}
VOLUNTEER = volunteer_headers()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "save_profile", lambda profile: None)  # don't write profiles/ during tests
    c = TestClient(main.app)
    c.post(F + "/reset", headers=VOLUNTEER)
    return c


def test_dashboard_load_reads_every_field_the_ui_uses(client):
    status = client.get(F + "/status").json()
    site = status["sites"][0]
    for field in ("id", "name", "facilities", "lat", "lng", "closed", "occupancy", "capacity",
                  "projected_next_slot_occupancy", "trend_people_per_hour", "status"):
        assert field in site
    assert {"fill", "forecast_fill"} <= set(site["waste"])
    assert "sim_time" in status

    festivals = client.get("/festivals").json()
    assert {"id", "name", "description", "sites", "hours"} <= set(festivals[0])
    assert client.get(F + "/swm/tasks").status_code == 200
    assert client.get(F + "/swm/routes").status_code == 200
    assert client.get(F + "/log?limit=50").status_code == 200
    assert client.get(F + "/my-groups", headers=DEMO).status_code == 200


def test_visitor_booking_and_my_groups(client):
    status = client.get(F + "/status").json()
    response = client.post(F + "/requests", headers=DEMO, json={
        "group_name": "visitor", "group_size": 4, "preferred_site_id": "lalbaugcha_raja",
        "preferred_time": status["sim_time"]})
    assert response.status_code == 200
    decision = response.json()["decision"]
    assert decision["decision"] in ("ALLOCATED", "DIVERTED", "REJECTED")
    assert {"reason", "assigned", "notifications"} <= set(decision)
    assert set(decision["notifications"]) == {"en", "hi", "mr"}

    groups = client.get(F + "/my-groups", headers=DEMO).json()
    assert groups and {"id", "name", "status", "site_name", "size", "slot_time", "reroutes", "latest_update"} <= set(groups[0])


def test_volunteer_controls(client):
    demo = client.post(F + "/demo/reroute", headers=VOLUNTEER).json()
    assert {"reroutes", "bookings", "site_name", "status_after"} <= set(demo)
    assert all("assigned" in b for b in demo["bookings"])

    body = {"reason": "Updated from UtsavSync volunteer console"}
    assert client.post(F + "/sites/ganesh_galli/close", headers=VOLUNTEER, json=body).status_code == 200
    assert client.post(F + "/sites/ganesh_galli/open", headers=VOLUNTEER, json=body).status_code == 200
    advanced = client.post(F + "/clock/advance", headers=VOLUNTEER, json={"minutes": 180}).json()
    assert "sim_time" in advanced

    # Crowd field report (waste fields sent as null), then a waste one (crowd sent as null).
    crowd = client.post(F + "/field-reports", headers=VOLUNTEER, json={
        "site_id": "ganesh_galli", "crowd_level": "HIGH", "waste_level_percent": None,
        "entries": 0, "exits": 0, "remarks": "Crowd issue: No additional details supplied"})
    assert crowd.status_code == 200, crowd.text
    waste = client.post(F + "/field-reports", headers=VOLUNTEER, json={
        "site_id": "ganesh_galli", "crowd_level": None, "waste_level_percent": 95,
        "entries": 0, "exits": 0, "remarks": "Waste overflow: bins full"})
    assert waste.status_code == 200, waste.text

    tasks = [t for t in client.get(F + "/swm/tasks").json() if t["status"] == "OPEN"]
    assert tasks and {"site_name", "priority", "expected_load_kg", "current_fill", "reason"} <= set(tasks[0])
    routes = client.get(F + "/swm/routes").json()
    assert routes and {"route_id", "priority", "stops", "distance_km", "expected_load_kg"} <= set(routes[0])
    done = client.post(F + f"/swm/tasks/{tasks[0]['id']}/complete", headers=VOLUNTEER, json={})
    assert done.status_code == 200 and done.json()["status"] == "COMPLETED"


def test_citizen_report(client):
    for body in ({"site_id": "lalbaugcha_raja", "reporter_type": "citizen", "kind": "crowd",
                  "crowd_level": "CRITICAL", "note": "Safety concern: pushing at gate"},
                 {"site_id": "lalbaugcha_raja", "reporter_type": "citizen", "kind": "waste",
                  "bin_fill_percent": 85, "note": "Waste overflow: none"}):
        assert client.post(F + "/reports", headers=DEMO, json=body).status_code == 200


@pytest.mark.parametrize("then_advance", [60, None, ""])
def test_what_if_accepts_blank_form_fields(client, then_advance):
    response = client.post(F + "/what-if", headers=VOLUNTEER, json={
        "action": "close_site", "site_id": "lalbaugcha_raja", "at_time": None,
        "extra_people": 250, "then_advance_minutes": then_advance})
    assert response.status_code == 200, response.text
    result = response.json()
    assert {"note", "summary", "sites_after"} <= set(result)
    assert {"status", "occupancy", "waste"} <= set(result["sites_after"][0])


def test_simulation(client):
    result = client.post(F + "/simulate", headers=VOLUNTEER, json={"events": 50, "replace_live": False}).json()
    assert result["summary"]["total_inputs"] == 50
    assert "sites" in result["status"] and "sim_time" in result["status"]


def test_adding_dahi_handi_twice_is_fine(client):
    profile = json.loads((FRONTEND_SRC / "dahi_handi.json").read_text(encoding="utf-8"))
    main.profiles.pop("dahi_handi", None)
    first = client.post("/festivals", headers=VOLUNTEER, json=profile)
    again = client.post("/festivals", headers=VOLUNTEER, json=profile)
    assert first.status_code == 201 and again.status_code == 200
    assert "already live" in again.json()["message"]
    changed = {**profile, "name": "Something else"}
    assert client.post("/festivals", headers=VOLUNTEER, json=changed).status_code == 409
    main.profiles.pop("dahi_handi", None)
    main.engines.pop("dahi_handi", None)


def test_real_login_identifies_user_even_with_auth_off(client, monkeypatch):
    """The frontend sends a Supabase token instead of X-User-Id once login is real."""
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setattr(auth, "_lookup", lambda token: auth.User("real-user-1", "a@b.in", "visitor", True))
    token = {"Authorization": "Bearer real-token", "X-Role": "visitor"}
    client.post(F + "/requests", headers=token, json={"group_size": 3, "preferred_site_id": "ganesh_galli"})
    mine = client.get(F + "/my-groups", headers=token)
    assert mine.status_code == 200 and len(mine.json()) == 1
