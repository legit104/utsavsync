"""Database layer: every row the backend writes must fit supabase_schema.sql."""

import re
from pathlib import Path

import httpx

from app.engine import FestivalEngine, to_hhmm
from app.profiles import load_profiles
from app.simulation import run_reroute_demo
from app.storage import SupabaseStorage

SCHEMA = (Path(__file__).resolve().parent.parent / "supabase_schema.sql").read_text(encoding="utf-8")
PROFILES = load_profiles()


def schema_columns() -> dict[str, dict[str, bool]]:
    """{table: {column: required}} where required = NOT NULL with no default."""
    tables = {}
    for name, body in re.findall(r"create table if not exists (\w+) \((.*?)\n\);", SCHEMA, re.S):
        columns = {}
        for line in body.splitlines():
            line = line.split("--")[0].strip().rstrip(",")
            match = re.match(r"(\w+)\s+(\w+)", line)
            if not match or match.group(1) in ("primary", "foreign", "unique", "check"):
                continue
            required = "not null" in line and "default" not in line and "primary key" not in line
            columns[match.group(1)] = required or "primary key" in line
        tables[name] = columns
    return tables


class RecordingStorage:
    def __init__(self):
        self.rows: dict[str, list[dict]] = {}

    def save(self, table, rows):
        self.rows.setdefault(table, []).extend([rows] if isinstance(rows, dict) else rows)


def test_schema_defines_every_table_the_backend_uses():
    assert {"profiles", "festivals", "sites", "site_status", "groups",
            "decision_log", "swm_tasks", "notifications"} <= set(schema_columns())


def test_every_written_row_matches_the_schema():
    storage = RecordingStorage()
    engine = FestivalEngine(PROFILES["ganesh_utsav"], storage)
    engine.advance(240)
    engine.allocate({"group_size": 20, "preferred_site_id": "lalbaugcha_raja",
                     "preferred_time": to_hhmm(engine.clock + 60), "requested_by": "user-1"})
    engine.allocate({"group_size": 500, "preferred_site_id": "lalbaugcha_raja", "requested_by": "user-2"})
    run_reroute_demo(engine, "lalbaugcha_raja")
    engine.report({"site_id": "ganesh_galli", "reporter_type": "volunteer", "kind": "waste", "bin_fill_percent": 100})
    engine.complete_task(next(iter(engine.swm_tasks)))
    engine.advance(120)
    engine.save_site_status()
    SupabaseStorage.sync_profile(storage, PROFILES["ganesh_utsav"])

    tables = schema_columns()
    assert {"decision_log", "groups", "notifications", "swm_tasks", "site_status", "festivals", "sites"} <= set(storage.rows)
    for table, rows in storage.rows.items():
        columns = tables[table]
        for row in rows:
            assert set(row) <= set(columns), f"{table} has unknown columns {set(row) - set(columns)}"
            missing = [c for c, required in columns.items() if required and row.get(c) is None]
            assert not missing, f"{table} row missing required {missing}: {row}"

    # A rejected visitor still gets their notification, and reroutes reach the right user.
    users = {n["user_id"] for n in storage.rows["notifications"]}
    assert {"user-1", "user-2"} <= users
    assert any(g["reroutes"] for g in storage.rows["groups"])


def test_storage_sends_correct_requests():
    sent = []

    def handler(request: httpx.Request):
        sent.append(request)
        return httpx.Response(201)

    storage = SupabaseStorage("https://x.supabase.co", "sb_secret_abc", background=False)
    storage.client._transport = httpx.MockTransport(handler)
    storage.save("site_status", [{"festival_id": "f", "site_id": "a", "crowd": 1},
                                 {"festival_id": "f", "site_id": "a", "crowd": 2}])
    storage.save("decision_log", {"id": "r-LOG-1"})

    status, log_write = sent
    assert status.url.path == "/rest/v1/site_status"
    assert status.url.params["on_conflict"] == "festival_id,site_id"
    assert status.read() == b'[{"festival_id":"f","site_id":"a","crowd":2}]'  # latest row wins
    assert "on_conflict" not in log_write.url.params
    assert status.headers["apikey"] == "sb_secret_abc" and "authorization" not in status.headers

    legacy = SupabaseStorage("https://x.supabase.co", "eyJlegacy", background=False)
    assert legacy.client.headers["authorization"] == "Bearer eyJlegacy"


def test_background_writes_keep_order_and_flush():
    order = []
    storage = SupabaseStorage("https://x.supabase.co", "sb_secret_abc")
    storage.client._transport = httpx.MockTransport(
        lambda r: order.append(r.url.path.rsplit("/", 1)[-1]) or httpx.Response(201))
    for table in ["festivals", "sites", "site_status", "site_status", "decision_log"]:
        storage.save(table, {"id": table, "festival_id": "f", "site_id": "s"})
    storage.flush()
    assert order == ["festivals", "sites", "site_status", "decision_log"]


def test_failed_writes_never_break_the_engine():
    storage = SupabaseStorage("https://x.supabase.co", "sb_secret_abc", background=False)
    storage.client._transport = httpx.MockTransport(lambda r: httpx.Response(500, text="boom"))
    engine = FestivalEngine(PROFILES["ganesh_utsav"], storage)
    assert engine.allocate({"group_size": 10, "preferred_site_id": "lalbaugcha_raja"})["decision"] == "ALLOCATED"
