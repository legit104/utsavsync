"""Optional Supabase persistence for the decision log and SWM tasks.

The engine keeps all live state in memory, so the API works without a
database. When SUPABASE_URL and SUPABASE_SERVICE_KEY are set, every decision
and task is also written to Supabase (tables in supabase_schema.sql) for
officials to query. Write failures are logged, never raised.
"""

from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger("festival.storage")


class SupabaseStorage:
    def __init__(self, url: str, key: str):
        self.client = httpx.Client(
            base_url=f"{url.rstrip('/')}/rest/v1",
            timeout=5,
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
        )

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
