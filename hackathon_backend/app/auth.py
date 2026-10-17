"""Identity resolution for visitor requests and approved volunteer sessions.

Visitors remain available in the demo. Volunteer-only actions require either a
valid Supabase app_metadata role or a signed, short-lived session issued after
a one-time database invite code is redeemed.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass

import httpx
from fastapi import Depends, Header, HTTPException

from .storage import tls_verify

ROLES = ("visitor", "volunteer")
CACHE_SECONDS = 60
VOLUNTEER_SESSION_SECONDS = 8 * 60 * 60
_cache: dict[str, tuple[float, "User"]] = {}


@dataclass
class User:
    id: str | None
    email: str | None
    role: str
    verified: bool

    @property
    def reporter_type(self) -> str:
        return "volunteer" if self.role == "volunteer" else "citizen"


def auth_enabled() -> bool:
    return os.getenv("AUTH_MODE", "off").lower() == "supabase"


def _session_secret() -> bytes:
    secret = os.getenv("VOLUNTEER_SESSION_SECRET")
    if not secret:
        raise HTTPException(503, "Volunteer sessions are not configured on this server")
    return secret.encode("utf-8")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def issue_volunteer_token(user_id: str, email: str) -> tuple[str, int]:
    expires = int(time.time()) + VOLUNTEER_SESSION_SECONDS
    payload = _b64(json.dumps({
        "sub": user_id, "email": email, "role": "volunteer", "exp": expires,
    }, separators=(",", ":")).encode("utf-8"))
    unsigned = "vs1." + payload
    signature = _b64(hmac.new(_session_secret(), unsigned.encode("ascii"), hashlib.sha256).digest())
    return unsigned + "." + signature, expires


def _volunteer_from_token(token: str) -> User:
    try:
        version, payload, signature = token.split(".", 2)
        unsigned = version + "." + payload
        expected = _b64(hmac.new(_session_secret(), unsigned.encode("ascii"), hashlib.sha256).digest())
        if version != "vs1" or not hmac.compare_digest(signature, expected):
            raise ValueError("bad signature")
        decoded = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        data = json.loads(decoded)
        if data.get("role") != "volunteer" or int(data.get("exp", 0)) <= time.time():
            raise ValueError("expired or wrong role")
        return User(str(data["sub"]), str(data["email"]), "volunteer", verified=True)
    except HTTPException:
        raise
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(401, "Volunteer session is invalid or expired") from exc


def _lookup(token: str) -> User:
    cached = _cache.get(token)
    if cached and cached[0] > time.time():
        return cached[1]
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        raise HTTPException(500, "AUTH_MODE=supabase needs SUPABASE_URL and SUPABASE_ANON_KEY in .env")
    try:
        response = httpx.get(f"{url.rstrip('/')}/auth/v1/user", timeout=5, verify=tls_verify(),
                             headers={"apikey": key, "Authorization": f"Bearer {token}"})
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Could not reach Supabase Auth") from exc
    if response.status_code != 200:
        raise HTTPException(401, "Login expired or invalid; please sign in again")
    data = response.json()
    # Only server-controlled app_metadata may grant a volunteer role.
    role = ((data.get("app_metadata") or {}).get("role") or "visitor").lower()
    user = User(data.get("id"), data.get("email"), role if role in ROLES else "visitor", verified=True)
    _cache[token] = (time.time() + CACHE_SECONDS, user)
    return user


def current_user(authorization: str | None = Header(None),
                 x_user_id: str | None = Header(None, description="Demo visitor id; never grants volunteer access")) -> User:
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if token.startswith("vs1."):
            return _volunteer_from_token(token)
        if auth_enabled():
            return _lookup(token)
        # Login not enforced, but a real Supabase login still identifies the user,
        # so bookings and "my groups" follow the account.
        if token and os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_ANON_KEY"):
            try:
                return _lookup(token)
            except HTTPException:
                pass
    if auth_enabled():
        raise HTTPException(401, "Sign in required: send 'Authorization: Bearer <access token>'")
    # X-Role is intentionally ignored. A browser cannot self-assign volunteer privileges.
    return User(x_user_id, None, "visitor", verified=False)


def require_volunteer(user: User = Depends(current_user)) -> User:
    if not user.verified or user.role != "volunteer":
        raise HTTPException(403, "A verified volunteer account and access code are required")
    return user
