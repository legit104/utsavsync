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
