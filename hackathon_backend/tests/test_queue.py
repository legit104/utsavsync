"""Waiting queue: when every nearby site is unsafe, groups wait and are placed automatically."""

import json

from fastapi.testclient import TestClient

from app import main
from app.engine import ARRIVED, CANCELLED, PENDING, QUEUED, FestivalEngine, distance_km
from app.profiles import load_profiles
from app.simulation import ease_queue_demo, run_queue_demo, warm_up
from conftest import volunteer_headers

PROFILES = load_profiles()
LALBAUG = "lalbaugcha_raja"


def busy_area(engine, keep_open=None, room_people=None):
    """Make every site near Lalbaug RED, optionally leaving one AMBER site with `room_people` spaces."""
    target = engine.sites[LALBAUG]
    for site in engine.sites.values():
        if distance_km(target.config, site.config) <= engine.rules["max_reroute_distance_km"]:
            site.crowd = round(site.capacity * 0.95)
    if keep_open:
        site = engine.sites[keep_open]
        site.crowd = int(site.capacity * engine.th["amber_max"]) - room_people
    engine._refresh()


def ganesh():
    return FestivalEngine(PROFILES["ganesh_utsav"])


def test_full_area_queues_instead_of_rejecting_and_releases_when_space_opens():
    engine = ganesh()
    busy_area(engine)
    first = engine.allocate({"group_name": "A", "group_size": 10, "preferred_site_id": LALBAUG, "requested_by": "v1"})
    second = engine.allocate({"group_name": "B", "group_size": 10, "preferred_site_id": LALBAUG})
    assert first["decision"] == second["decision"] == QUEUED
    assert (first["queue_position"], second["queue_position"]) == (1, 2)
    assert "#1 in the queue" in first["notifications"]["en"]

    galli = engine.sites["ganesh_galli"]
    galli.crowd = round(galli.capacity * 0.3)  # the crowd eases at one site
    engine._refresh(["ganesh_galli"])

    released = [e for e in engine.log if e["type"] == "QUEUE_RELEASE"]
    assert [e["group"]["name"] for e in released] == ["A", "B"]  # first come, first served
    assert all(e["assigned"]["site_id"] == "ganesh_galli" for e in released)
    assert not engine.queue()
    assert {engine.groups[e["group"]["id"]].status for e in released} <= {PENDING, ARRIVED}
    assert galli.status != "RED"  # releases never push a site back into RED


def test_first_that_fits_but_the_front_group_is_overtaken_at_most_three_times():
    engine = ganesh()
    busy_area(engine, keep_open="khetwadi_ganraj", room_people=0)
    big = engine.allocate({"group_name": "Big", "group_size": 50, "preferred_site_id": LALBAUG})
    smalls = [engine.allocate({"group_name": f"Small {i}", "group_size": 5, "preferred_site_id": LALBAUG})
              for i in range(6)]
    assert big["decision"] == QUEUED and all(s["decision"] == QUEUED for s in smalls)

    khetwadi = engine.sites["khetwadi_ganraj"]
    placed_names = []
    for _ in range(5):  # five rounds, each opening room for exactly one small group (but never for Big)
        khetwadi.crowd -= 5
        engine._refresh(["khetwadi_ganraj"])
        placed_names = [e["group"]["name"] for e in engine.log if e["type"] == "QUEUE_RELEASE"]

    big_group = engine.groups[big["group"]["id"]]
    assert placed_names == ["Small 0", "Small 1", "Small 2"]  # three overtakes, then the line holds
    assert big_group.status == QUEUED and big_group.skips == 3
    assert engine.queue()[0] is big_group


def test_waiting_too_long_releases_the_group_with_an_apology():
    engine = ganesh()
    busy_area(engine)
    queued = engine.allocate({"group_name": "Late", "group_size": 10, "preferred_site_id": LALBAUG})
    engine.advance(engine.rules["queue_max_wait_minutes"] - 5)  # the area stays packed (no walk-in feed here)
    group = engine.groups[queued["group"]["id"]]
    assert group.status == QUEUED  # still within the waiting limit
    engine.advance(10)
    expired = [e for e in engine.log if e["type"] == "QUEUE_EXPIRED"]
    assert group.status == CANCELLED and [e["group"]["id"] for e in expired] == [group.id]
    assert "Sorry" in expired[0]["notifications"]["en"]
    assert not [e for e in engine.log if e["type"] == "QUEUE_RELEASE"]


def test_group_that_cannot_be_rerouted_waits_instead_of_being_cancelled():
    engine = ganesh()
    booked = engine.allocate({"group_size": 10, "preferred_site_id": LALBAUG,
                              "preferred_time": "07:00"})
    assert booked["decision"] == "ALLOCATED"
    busy_area(engine)
    group = engine.groups[booked["group"]["id"]]
    assert group.status == QUEUED
    assert any(e["type"] == "REROUTE" and e["decision"] == QUEUED for e in engine.log)


def test_full_or_disabled_queue_still_rejects():
    profile = json.loads(json.dumps(PROFILES["ganesh_utsav"]))
    profile["rules"]["max_queue_size"] = 1
    engine = FestivalEngine(profile)
    busy_area(engine)
    assert engine.allocate({"group_size": 5, "preferred_site_id": LALBAUG})["decision"] == QUEUED
    second = engine.allocate({"group_size": 5, "preferred_site_id": LALBAUG})
    assert second["decision"] == "REJECTED" and "queue is also full" in second["reason"]

    profile["rules"]["queue_enabled"] = False
    engine = FestivalEngine(profile)
    busy_area(engine)
    assert engine.allocate({"group_size": 5, "preferred_site_id": LALBAUG})["decision"] == "REJECTED"


def test_queue_survives_a_restart():
    engine = ganesh()
    busy_area(engine)
    engine.allocate({"group_name": "Waiting", "group_size": 10, "preferred_site_id": LALBAUG})
    restored = FestivalEngine.from_state(PROFILES["ganesh_utsav"], json.loads(json.dumps(engine.to_state())))
    assert [g.name for g in restored.queue()] == ["Waiting"]
    assert restored.snapshot()["queue"] == engine.snapshot()["queue"]


def test_queue_demo_and_api():
    engine = warm_up(ganesh())
    demo = run_queue_demo(engine)
    assert demo["queued"] == 3 and all(s["status"] == "RED" for s in demo["area"])
    eased = ease_queue_demo(engine, demo["ease_site_id"])
    assert len(eased["released"]) == 3 and eased["still_waiting"] == 0

    client = TestClient(main.app)
    vol = volunteer_headers()
    client.post("/festivals/ganesh_utsav/reset", headers=vol)
    visitor = {"X-User-Id": "queue-visitor"}
    busy = client.post("/festivals/ganesh_utsav/demo/queue", headers=vol).json()
    mine = client.post("/festivals/ganesh_utsav/requests", headers=visitor,
                       json={"group_size": 6, "preferred_site_id": LALBAUG}).json()["decision"]
    assert mine["decision"] == QUEUED
    status = client.get("/festivals/ganesh_utsav/status").json()
    assert len(status["queue"]) == 4
    groups = client.get("/festivals/ganesh_utsav/my-groups", headers=visitor).json()
    assert groups[0]["status"] == QUEUED and groups[0]["queue_position"] == 4

    client.post("/festivals/ganesh_utsav/demo/queue/ease", headers=vol, params={"site_id": busy["ease_site_id"]})
    groups = client.get("/festivals/ganesh_utsav/my-groups", headers=visitor).json()
    assert groups[0]["status"] in (PENDING, ARRIVED) and groups[0]["queue_position"] is None
    assert groups[0]["latest_update"]["type"] == "QUEUE_RELEASE"
    assert client.post("/festivals/ganesh_utsav/demo/queue", headers=visitor).status_code == 403
