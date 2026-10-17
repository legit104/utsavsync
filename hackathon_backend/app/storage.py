"""Optional Supabase persistence for the decision log and SWM tasks.

The engine keeps all live state in memory, so the API works without a
database. When SUPABASE_URL and SUPABASE_SERVICE_KEY are set, every decision
and task is also written to Supabase (tables in supabase_schema.sql) for
officials to query. Write failures are logged, never raised.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx

log = logging.getLogger("festival.storage")


class SupabaseStorage:
    def __init__(self, url: str, key: str):
        headers = {
            "apikey": key,
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
        # Legacy service_role keys are JWTs and also go in Authorization;
        # new sb_secret_ keys are not JWTs and must only be sent as apikey.
        if not key.startswith("sb_"):
            headers["Authorization"] = f"Bearer {key}"
        self.client = httpx.Client(base_url=f"{url.rstrip('/')}/rest/v1", timeout=5, headers=headers)


    def redeem_volunteer_code(self, email: str, code_hash: str) -> dict | None:
        """Atomically consume one active, email-bound volunteer invitation."""
        now = datetime.now(timezone.utc).isoformat()
        response = self.client.patch(
            "/volunteer_access_codes",
            params={
                "select": "id,email",
                "email": f"eq.{email.lower()}",
                "code_hash": f"eq.{code_hash}",
                "redeemed_at": "is.null",
                "expires_at": f"gt.{now}",
            },
            json={"redeemed_at": now, "redeemed_by": email.lower()},
            headers={"Prefer": "return=representation"},
        )
        response.raise_for_status()
        rows = response.json()
        return rows[0] if rows else None
    def save(self, table: str, rows: dict | list[dict]) -> None:
        if not rows:
            return
        try:
            self.client.post(f"/{table}", json=rows).raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("Supabase write to %s failed: %s", table, exc)


def storage_from_env() -> SupabaseStorage | None:
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY")
    return SupabaseStorage(url, key) if url and key else None

