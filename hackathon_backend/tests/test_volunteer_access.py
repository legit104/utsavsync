"""Volunteer access: only a redeemed one-time code (or an admin-set role) grants volunteer powers."""

import hashlib
import time

import pytest
from fastapi.testclient import TestClient

from app import auth, main
from conftest import volunteer_headers
from test_storage import schema_columns

F = "/festivals/ganesh_utsav"
REPORT = {"site_id": "ganesh_galli", "crowd_level": "HIGH"}


class FakeCodes:
    """Stands in for the volunteer_access_codes table."""

    def __init__(self, email, code):
        self.valid = {(email, hashlib.sha256(code.encode()).hexdigest())}

    def redeem_volunteer_code(self, email, code_hash):
        key = (email, code_hash)
        if key in self.valid:
            self.valid.remove(key)  # one use only
            return {"id": "code-1", "email": email}
        return None


@pytest.fixture
def client():
    return TestClient(main.app)


def test_claiming_volunteer_in_a_header_grants_nothing(client):
    fake = {"X-User-Id": "someone", "X-Role": "volunteer"}
    assert client.post(F + "/field-reports", headers=fake, json=REPORT).status_code == 403
    assert client.post(F + "/reset", headers=fake).status_code == 403


def test_signed_volunteer_pass_works_and_tampering_fails(client):
    good = volunteer_headers()
    assert client.post(F + "/field-reports", headers=good, json=REPORT).status_code == 200
    tampered = {"Authorization": good["Authorization"][:-2] + "xx"}
    assert client.post(F + "/field-reports", headers=tampered, json=REPORT).status_code == 401


def test_expired_volunteer_pass_is_rejected(client, monkeypatch):
    headers = volunteer_headers()
    monkeypatch.setattr(time, "time", lambda: 10**10)  # far in the future
    assert client.post(F + "/field-reports", headers=headers, json=REPORT).status_code == 401


def test_redeeming_a_code_issues_a_working_pass_once(client, monkeypatch):
    monkeypatch.setattr(main, "storage", FakeCodes("vol@utsavsync.in", "correct-code-123"))
    wrong = client.post("/volunteers/verify-code", json={"email": "vol@utsavsync.in", "access_code": "wrong-code-0000"})
    assert wrong.status_code == 403

    first = client.post("/volunteers/verify-code", json={"email": "VOL@utsavsync.in ", "access_code": "correct-code-123"})
    assert first.status_code == 200, first.text
    token = first.json()["access_token"]
    assert token.startswith("vs1.") and first.json()["role"] == "volunteer"
    me = client.get("/me", headers={"Authorization": "Bearer " + token}).json()
    assert me["role"] == "volunteer" and me["email"] == "vol@utsavsync.in"

    again = client.post("/volunteers/verify-code", json={"email": "vol@utsavsync.in", "access_code": "correct-code-123"})
    assert again.status_code == 403  # already used


def test_code_for_another_email_is_rejected(client, monkeypatch):
    monkeypatch.setattr(main, "storage", FakeCodes("vol@utsavsync.in", "correct-code-123"))
    other = client.post("/volunteers/verify-code", json={"email": "thief@utsavsync.in", "access_code": "correct-code-123"})
    assert other.status_code == 403


def test_codes_need_database_and_secret(client, monkeypatch):
    body = {"email": "vol@utsavsync.in", "access_code": "correct-code-123"}
    monkeypatch.setattr(main, "storage", None)
    assert client.post("/volunteers/verify-code", json=body).status_code == 503
    monkeypatch.setattr(main, "storage", FakeCodes("vol@utsavsync.in", "correct-code-123"))
    monkeypatch.delenv("VOLUNTEER_SESSION_SECRET")
    assert client.post("/volunteers/verify-code", json=body).status_code == 503


def test_sign_up_role_never_makes_a_volunteer(monkeypatch):
    """A Supabase user who picked 'volunteer' at sign-up is still a visitor; only app_metadata counts."""
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")

    class Reply:
        status_code = 200

        def json(self):
            return {"id": "u1", "email": "a@b.in", "user_metadata": {"role": "volunteer"}}

    monkeypatch.setattr(auth.httpx, "get", lambda *a, **k: Reply())
    auth._cache.clear()
    assert auth._lookup("token").role == "visitor"


def test_schema_has_volunteer_codes_table():
    columns = schema_columns()["volunteer_access_codes"]
    assert {"email", "code_hash", "expires_at", "redeemed_at"} <= set(columns)


def test_storage_redeems_through_database_function():
    import httpx
    from app.storage import SupabaseStorage

    sent = []
    replies = iter([[{"code_id": "c1", "redeemed_email": "vol@utsavsync.in"}], []])

    def handler(request):
        sent.append(request)
        return httpx.Response(200, json=next(replies))

    storage = SupabaseStorage("https://x.supabase.co", "sb_secret_abc", background=False)
    storage.client._transport = httpx.MockTransport(handler)
    assert storage.redeem_volunteer_code("VOL@utsavsync.in", "hash1") == {"id": "c1", "email": "vol@utsavsync.in"}
    assert storage.redeem_volunteer_code("vol@utsavsync.in", "hash1") is None  # used up / wrong email
    assert sent[0].url.path == "/rest/v1/rpc/redeem_volunteer_code"
    assert sent[0].read() == b'{"p_code_hash":"hash1","p_email":"vol@utsavsync.in"}'


@pytest.mark.parametrize("args, message", [
    ([], "either a volunteer email address or --any-email"),
    (["a@b.in", "--any-email"], "either a volunteer email address or --any-email"),
    (["--any-email", "--uses", "0"], "--uses must be between 1 and 1000"),
])
def test_code_script_rejects_bad_options(args, message):
    import subprocess
    import sys
    from pathlib import Path

    env = {**__import__("os").environ, "SUPABASE_URL": "https://x.supabase.co", "SUPABASE_SERVICE_KEY": "sb_secret_x"}
    result = subprocess.run([sys.executable, "issue_volunteer_code.py", *args], capture_output=True, text=True,
                            cwd=Path(__file__).resolve().parent.parent, env=env, timeout=60)
    assert result.returncode != 0 and message in result.stderr


def test_schema_supports_open_codes_with_use_limits():
    from test_storage import SCHEMA
    columns = schema_columns()["volunteer_access_codes"]
    assert {"max_uses", "use_count"} <= set(columns) and columns["email"] is False  # email optional
    assert "create or replace function public.redeem_volunteer_code" in SCHEMA
    assert "(c.email is null or c.email = lower(p_email))" in SCHEMA
    assert "c.use_count < c.max_uses" in SCHEMA


def test_wifi_mode_accepts_private_addresses_only(monkeypatch):
    """start-lan.bat's CORS pattern: laptops on the same Wi-Fi yes, other websites no."""
    import re
    from pathlib import Path

    bat = (Path(__file__).resolve().parent.parent / "start.bat").read_text(encoding="utf-8")
    pattern = re.search(r'set "CORS_ORIGIN_REGEX=(.+)"', bat).group(1)
    for origin in ("http://192.168.1.25:5173", "http://10.0.0.7:5173", "http://172.20.3.4:5173", "http://localhost:5173"):
        assert re.fullmatch(pattern, origin), origin
    for origin in ("http://evil.example:5173", "http://192.168.1.25.evil.example:5173", "http://8.8.8.8:5173",
                   "http://172.32.0.1:5173", "http://192.168.1.25:8080"):
        assert not re.fullmatch(pattern, origin), origin
