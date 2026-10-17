"""The live festival survives a backend restart (e.g. after editing backend code)."""

import json

from fastapi.testclient import TestClient

from app import main
from app.engine import FestivalEngine
from app.profiles import load_profiles
from app.simulation import run_reroute_demo, warm_up
from conftest import volunteer_headers

PROFILE = load_profiles()["ganesh_utsav"]
F = "/festivals/ganesh_utsav"


def test_engine_round_trip_keeps_everything():
    engine = warm_up(FestivalEngine(PROFILE))
    run_reroute_demo(engine)
    engine.close_site("khetwadi_ganraj", "test")
    engine.allocate({"group_size": 10, "preferred_site_id": "girgaon_chowpatty", "requested_by": "visitor-1"})

    restored = FestivalEngine.from_state(PROFILE, json.loads(json.dumps(engine.to_state())))

    assert restored.snapshot() == engine.snapshot()
    assert restored.log == engine.log and restored.run_id == engine.run_id
    assert {g.id: g.site_id for g in restored.groups.values()} == {g.id: g.site_id for g in engine.groups.values()}
    # Carries on exactly where it left off: the next ids continue the same sequence.
    a = engine.allocate({"group_size": 5, "preferred_site_id": "ganesh_galli"})
    b = restored.allocate({"group_size": 5, "preferred_site_id": "ganesh_galli"})
    assert a["id"] == b["id"] and a["decision"] == b["decision"]


def test_changes_are_saved_and_restored_after_a_restart():
    client = TestClient(main.app)
    client.post(F + "/reset", headers=volunteer_headers())
    client.post(F + "/sites/khetwadi_ganraj/close", headers=volunteer_headers(), json={"reason": "before restart"})
    before = client.get(F + "/status").json()

    # Simulate the backend restarting: throw the in-memory engine away and start it again.
    main.engines.pop("ganesh_utsav")
    main.start_engine(main.profiles["ganesh_utsav"])

    after = client.get(F + "/status").json()
    assert after == before
    assert next(s for s in after["sites"] if s["id"] == "khetwadi_ganraj")["closed"] is True


def test_reset_is_saved_too():
    client = TestClient(main.app)
    client.post(F + "/sites/ganesh_galli/close", headers=volunteer_headers(), json={"reason": "x"})
    client.post(F + "/reset", headers=volunteer_headers())
    main.engines.pop("ganesh_utsav")
    main.start_engine(main.profiles["ganesh_utsav"])
    sites = client.get(F + "/status").json()["sites"]
    assert not any(s["closed"] for s in sites)


def test_a_changed_profile_or_broken_file_starts_fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "STATE_DIR", tmp_path)
    engine = warm_up(FestivalEngine(PROFILE))
    engine.close_site("ganesh_galli", "x")
    main.save_state(engine)
    assert main.load_state(PROFILE) is not None

    edited = json.loads(json.dumps(PROFILE))
    edited["sites"][0]["capacity"] += 100
    assert main.load_state(edited) is None  # profile changed: don't load an old day into it

    (tmp_path / "ganesh_utsav.json").write_text("{not json", encoding="utf-8")
    assert main.load_state(PROFILE) is None  # unreadable: start fresh instead of crashing
