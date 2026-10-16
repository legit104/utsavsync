"""Login and roles (Visitor / Volunteer) using Supabase Auth.

AUTH_MODE=off (default): nothing is checked, so the frontend can integrate
before Supabase is set up. Send `X-User-Id` to fake a logged-in user.

AUTH_MODE=supabase: protected calls need `Authorization: Bearer <access token>`
from supabase.auth.signInWithPassword(). The backend asks Supabase who the
token belongs to and reads the role from, in order: app_metadata.role (set by
an admin), the `profiles` table (created on sign-up, not editable by users),
then user_metadata.role. Anything else is treated as a visitor.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Callable

import httpx
from fastapi import Depends, Header, HTTPException

ROLES = ("visitor", "volunteer")
CACHE_SECONDS = 60
_cache: dict[str, tuple[float, "User"]] = {}
# Set by main.py when Supabase storage is configured: user id -> role from the profiles table.
role_lookup: Callable[[str], str | None] | None = None


@dataclass
class User:
    id: str | None
    email: str | None
    role: str
    verified: bool  # False when AUTH_MODE=off: nothing was checked

    @property
    def reporter_type(self) -> str:
        return "volunteer" if self.role == "volunteer" else "citizen"


def auth_enabled() -> bool:
    return os.getenv("AUTH_MODE", "off").lower() == "supabase"


def _lookup(token: str) -> User:
    cached = _cache.get(token)
    if cached and cached[0] > time.time():
        return cached[1]
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        raise HTTPException(500, "AUTH_MODE=supabase needs SUPABASE_URL and SUPABASE_ANON_KEY in .env")
    try:
        response = httpx.get(f"{url.rstrip('/')}/auth/v1/user", timeout=5,
                             headers={"apikey": key, "Authorization": f"Bearer {token}"})
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Could not reach Supabase Auth") from exc
    if response.status_code != 200:
        raise HTTPException(401, "Login expired or invalid; please sign in again")
    data = response.json()
    role = ((data.get("app_metadata") or {}).get("role")
            or (role_lookup(data["id"]) if role_lookup and data.get("id") else None)
            or (data.get("user_metadata") or {}).get("role") or "visitor").lower()
    user = User(data.get("id"), data.get("email"), role if role in ROLES else "visitor", verified=True)
    _cache[token] = (time.time() + CACHE_SECONDS, user)
    return user


def current_user(authorization: str | None = Header(None),
                 x_user_id: str | None = Header(None, description="Dev only (AUTH_MODE=off): fake user id"),
                 x_role: str | None = Header(None, description="Dev only (AUTH_MODE=off): visitor or volunteer")) -> User:
    if not auth_enabled():
        role = (x_role or "visitor").lower()
        return User(x_user_id, None, role if role in ROLES else "visitor", verified=False)
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Sign in required: send 'Authorization: Bearer <access token>'")
    return _lookup(authorization.split(" ", 1)[1].strip())


def require_volunteer(user: User = Depends(current_user)) -> User:
    if user.verified and user.role != "volunteer":
        raise HTTPException(403, "Only volunteers can do this")
    return user
