"""Optional Supabase persistence (tables in supabase_schema.sql).

The engine keeps all live state in memory, so the API works without a
database. When SUPABASE_URL and SUPABASE_SERVICE_KEY are set:

* festival profiles and their sites are synced to the database on startup,
  and festivals that exist only in the `festivals` table are loaded too;
* every decision, group, SWM task, notification and live site status is
  written as it happens;
* one-time volunteer access codes are checked and redeemed.

Writes go through a background thread, in order, so a slow network never
slows the API down. Failures are logged, never raised.
"""

from __future__ import annotations

import logging
import os
import queue
import ssl
import threading
from datetime import datetime, timezone

import httpx

log = logging.getLogger("festival.storage")


def tls_verify() -> ssl.SSLContext | bool:
    """Trust the same certificates as Windows/macOS (and the browser).

    Antivirus web shields (e.g. Norton) and college/office networks re-sign HTTPS
    traffic with their own certificate, which the OS trusts but Python's bundled
    list does not, so plain httpx fails with CERTIFICATE_VERIFY_FAILED.
    """
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return True

# Upsert key per table when it is not just "id" (PostgREST on_conflict).
CONFLICT_KEYS = {"sites": "festival_id,id", "site_status": "festival_id,site_id"}
BATCH_LIMIT = 500


class SupabaseStorage:
    def __init__(self, url: str, key: str, background: bool = True):
        headers = {
            "apikey": key,
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
        # Legacy service_role keys are JWTs and also go in Authorization;
        # new sb_secret_ keys are not JWTs and must only be sent as apikey.
        if not key.startswith("sb_"):
            headers["Authorization"] = f"Bearer {key}"
        self.client = httpx.Client(base_url=f"{url.rstrip('/')}/rest/v1", timeout=10, headers=headers,
                                   verify=tls_verify())
        self.background = background
        self._queue: queue.Queue[tuple[str, list[dict]]] = queue.Queue()
        if background:
            threading.Thread(target=self._worker, name="supabase-writer", daemon=True).start()

    # ---------------------------------------------------------------- writes

    def save(self, table: str, rows: dict | list[dict]) -> None:
        rows = [rows] if isinstance(rows, dict) else list(rows)
        if not rows:
            return
        if self.background:
            self._queue.put((table, rows))
        else:
            self._post(table, rows)

    def flush(self) -> None:
        """Wait until every queued write has been sent (used by tests and shutdown)."""
        if self.background:
            self._queue.join()

    def _worker(self) -> None:
        while True:
            batch = [self._queue.get()]
            # Grab whatever else is already waiting, keeping order.
            while not self._queue.empty():
                batch.append(self._queue.get())
            try:
                for table, rows in self._merge_consecutive(batch):
                    self._post(table, rows)
            finally:
                for _ in batch:
                    self._queue.task_done()

    @staticmethod
    def _merge_consecutive(batch):
        """Join neighbouring writes to the same table into one request, without reordering."""
        merged: list[tuple[str, list[dict]]] = []
        for table, rows in batch:
            if merged and merged[-1][0] == table and len(merged[-1][1]) + len(rows) <= BATCH_LIMIT:
                merged[-1][1].extend(rows)
            else:
                merged.append((table, list(rows)))
        return merged

    def _post(self, table: str, rows: list[dict]) -> None:
        # Later rows for the same key win (e.g. a group updated twice in one batch).
        key_cols = CONFLICT_KEYS.get(table, "id").split(",")
        latest = {tuple(r.get(k) for k in key_cols): r for r in rows}
        params = {"on_conflict": CONFLICT_KEYS[table]} if table in CONFLICT_KEYS else None
        try:
            self.client.post(f"/{table}", json=list(latest.values()), params=params).raise_for_status()
        except httpx.HTTPStatusError as exc:
            log.warning("Supabase write to %s failed: %s %s", table, exc.response.status_code, exc.response.text[:300])
        except httpx.HTTPError as exc:
            log.warning("Supabase write to %s failed: %s", table, exc)

    # ----------------------------------------------------------------- reads

    def load_profiles(self) -> list[dict]:
        """Festival profiles stored in the database (empty list if unreachable)."""
        try:
            response = self.client.get("/festivals", params={"select": "profile"})
            response.raise_for_status()
            return [row["profile"] for row in response.json() if row.get("profile")]
        except httpx.HTTPError as exc:
            log.warning("Could not load festivals from Supabase, using JSON files: %s", exc)
            return []

    def redeem_volunteer_code(self, email: str, code_hash: str) -> dict | None:
        """Atomically consume one active, email-bound volunteer invitation (raises on network errors)."""
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

    # ------------------------------------------------------- profile sync

    def sync_profile(self, profile: dict) -> None:
        """Write a festival and its sites (sites after the festival they belong to)."""
        day = profile["day"]
        self.save("festivals", {
            "id": profile["id"], "name": profile["name"], "description": profile.get("description", ""),
            "day_start": day["start"], "day_end": day["end"], "slot_minutes": day["slot_minutes"],
            "profile": profile,
        })
        self.save("sites", [{
            "festival_id": profile["id"], "id": s["id"], "name": s["name"], "lat": s["lat"], "lng": s["lng"],
            "capacity": s["capacity"], "open_time": s.get("open"), "close_time": s.get("close"),
            "facilities": s.get("facilities", []), "bin_count": s["bins"]["count"],
            "bin_capacity_kg": s["bins"]["capacity_kg"], "popularity": s.get("popularity", 1.0),
        } for s in profile["sites"]])


def storage_from_env() -> SupabaseStorage | None:
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY")
    return SupabaseStorage(url, key) if url and key else None
