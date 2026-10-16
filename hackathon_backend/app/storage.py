"""Optional Supabase persistence (tables in supabase_schema.sql).

The engine keeps all live state in memory, so the API works without a
database. When SUPABASE_URL and SUPABASE_SERVICE_KEY are set:

* festival profiles and their sites are synced to the database on startup,
  and profiles edited in the `festivals` table override the JSON files;
* every decision, group, SWM task, notification and live site status is
  written as it happens.

Writes go through a background thread, in order, so a slow network never
slows the API down. Failures are logged, never raised.
"""

from __future__ import annotations

import logging
import os
import queue
import threading

import httpx

log = logging.getLogger("festival.storage")

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
        self.client = httpx.Client(base_url=f"{url.rstrip('/')}/rest/v1", timeout=10, headers=headers)
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

    def user_role(self, user_id: str) -> str | None:
        """Role from the profiles table, which only the backend can change."""
        try:
            response = self.client.get("/profiles", params={"select": "role", "id": f"eq.{user_id}"})
            response.raise_for_status()
            rows = response.json()
            return rows[0]["role"] if rows else None
        except httpx.HTTPError as exc:
            log.warning("Could not read profile role: %s", exc)
            return None

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
