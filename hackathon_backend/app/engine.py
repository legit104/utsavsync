"""Festival Operations Engine.

Rule-based core that allocates groups to sites and time slots, tracks crowd
status, reroutes groups automatically when a site turns RED, and raises SWM
pickup tasks before bins overflow. Every number it uses comes from the
festival profile, so a new festival is a new JSON file, not new code.

Time is simulated: `clock` is minutes since midnight on the festival day.
"""

from __future__ import annotations

import copy
import math
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from .i18n import notify

GREEN, AMBER, RED, CLOSED = "GREEN", "AMBER", "RED", "CLOSED"
PENDING, ARRIVED, LEFT, CANCELLED = "PENDING", "ARRIVED", "LEFT", "CANCELLED"

# What a crowd report level means, as a fraction of site capacity.
LEVEL_FRACTION = {"LOW": 0.3, "MEDIUM": 0.65, "HIGH": 0.9, "CRITICAL": 1.1}
PRIORITY_RANK = {"URGENT": 0, "HIGH": 1, "NORMAL": 2}
TICK_MINUTES = 5
TREND_WINDOW_MINUTES = 30


class NotFoundError(KeyError):
    pass


def to_min(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pct(ratio: float) -> str:
    return f"{ratio:.0%}"


def distance_km(a: dict, b: dict) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (a["lat"], a["lng"], b["lat"], b["lng"]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


@dataclass
class Group:
    id: str
    name: str
    size: int
    site_id: str
    slot_start: int
    status: str = PENDING  # PENDING -> ARRIVED -> LEFT, or CANCELLED
    arrived_at: int | None = None
    reroutes: int = 0
    requested_by: str | None = None  # user id of the visitor who booked

    def to_dict(self) -> dict:
        return {**asdict(self), "slot_time": to_hhmm(self.slot_start)}


@dataclass
class Site:
    config: dict
    crowd: int = 0
    waste_kg: float = 0.0
    closed: bool = False
    status: str = GREEN
    samples: list = field(default_factory=list)  # recent (minute, crowd) readings for trend

    @property
    def id(self) -> str:
        return self.config["id"]

    @property
    def name(self) -> str:
        return self.config["name"]

    @property
    def capacity(self) -> int:
        return self.config["capacity"]

    @property
    def occupancy(self) -> float:
        return self.crowd / self.capacity

    @property
    def bin_capacity_kg(self) -> float:
        return self.config["bins"]["count"] * self.config["bins"]["capacity_kg"]


class FestivalEngine:
    def __init__(self, profile: dict, storage=None):
        self.profile = profile
        self.id = profile["id"]
        self.name = profile["name"]
        self.storage = storage
        self.run_id = uuid.uuid4().hex[:8]
        self.day_start = to_min(profile["day"]["start"])
        self.day_end = to_min(profile["day"]["end"])
        self.slot = profile["day"]["slot_minutes"]
        self.th = profile["thresholds"]
        self.rules = profile["rules"]
        self.waste = profile["waste"]
        self.rate_per_person_hour = sum(self.waste["per_person_per_hour_kg"].values())
        self.clock = self.day_start
        self.sites = {s["id"]: Site(s) for s in profile["sites"]}
        self.groups: dict[str, Group] = {}
        self.swm_tasks: dict[str, dict] = {}
        self.log: list[dict] = []
        self._seq = 0
        self._warned: set[tuple[str, int]] = set()

    # ------------------------------------------------------------------ helpers

    def _next_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}-{self._seq:04d}"

    def site(self, site_id: str) -> Site:
        try:
            return self.sites[site_id]
        except KeyError:
            raise NotFoundError(f"Unknown site '{site_id}' for festival '{self.id}'") from None

    def status_for(self, ratio: float) -> str:
        if ratio < self.th["green_max"]:
            return GREEN
        if ratio <= self.th["amber_max"]:
            return AMBER
        return RED

    def slot_of(self, minute: int) -> int:
        return self.day_start + (minute - self.day_start) // self.slot * self.slot

    def is_open(self, site: Site, slot_start: int) -> bool:
        opens = to_min(site.config.get("open") or self.profile["day"]["start"])
        closes = to_min(site.config.get("close") or self.profile["day"]["end"])
        return not site.closed and opens <= slot_start < closes

    def pending_load(self, site_id: str, slot_start: int | None = None) -> int:
        return sum(
            g.size
            for g in self.groups.values()
            if g.status == PENDING and g.site_id == site_id and (slot_start is None or g.slot_start == slot_start)
        )

    def projected_ratio(self, site: Site, slot_start: int, extra: int = 0) -> float:
        # Every request is judged on current crowd + groups already allocated + the new group.
        return (site.crowd + self.pending_load(site.id, slot_start) + extra) / site.capacity

    # ------------------------------------------------------ database rows
    # One builder per table in supabase_schema.sql. Ids are prefixed with the
    # run id so restarts and simulations never overwrite each other.

    def _db_id(self, local_id: str | None) -> str | None:
        return f"{self.run_id}-{local_id}" if local_id else None

    def _row(self, local_id: str, **columns) -> dict:
        return {"id": self._db_id(local_id), "run_id": self.run_id, "festival_id": self.id, **columns}

    def _log_row(self, entry: dict) -> dict:
        return self._row(entry["id"], type=entry["type"], sim_time=entry["sim_time"], payload=entry)

    def _notification_row(self, entry: dict) -> dict:
        group = entry.get("group") or {}
        site_id = (entry.get("to_site_id") or (entry.get("assigned") or {}).get("site_id")
                   or entry.get("site_id") or group.get("site_id"))
        messages = entry["notifications"]
        user_id = group.get("requested_by") or entry.get("requested_by")
        return self._row(entry["id"], type=entry["type"], user_id=user_id,
                         group_id=self._db_id(group.get("id")), site_id=site_id,
                         message_en=messages["en"], message_hi=messages.get("hi"), message_mr=messages.get("mr"))

    def _group_row(self, group: Group) -> dict:
        return self._row(group.id, requested_by=group.requested_by, name=group.name, size=group.size,
                         site_id=group.site_id, slot_time=to_hhmm(group.slot_start), status=group.status,
                         reroutes=group.reroutes, payload=group.to_dict(), updated_at=_now())

    def _task_row(self, task: dict) -> dict:
        return self._row(task["id"], site_id=task["site_id"], status=task["status"],
                         priority=task["priority"], payload=task, updated_at=_now())

    def _status_rows(self) -> list[dict]:
        rows = []
        for site in self.sites.values():
            view = self.site_view(site)
            rows.append({
                "festival_id": self.id, "site_id": site.id, "run_id": self.run_id, "sim_time": to_hhmm(self.clock),
                "status": site.status, "crowd": site.crowd, "occupancy": view["occupancy"],
                "pending_next_slot": view["pending_next_slot"], "waste_kg": view["waste"]["current_kg"],
                "bin_fill": view["waste"]["fill"], "forecast_fill": view["waste"]["forecast_fill"],
                "updated_at": _now(),
            })
        return rows

    def _save(self, table: str, rows) -> None:
        if self.storage:
            self.storage.save(table, rows)

    def _save_group(self, group: Group) -> None:
        self._save("groups", self._group_row(group))

    def save_site_status(self) -> None:
        """Write every site's live crowd and bin levels (called after each API change)."""
        self._save("site_status", self._status_rows())

    def _log(self, type_: str, **fields) -> dict:
        entry = {
            "id": self._next_id("LOG"),
            "festival_id": self.id,
            "type": type_,
            "sim_time": to_hhmm(self.clock),
            "logged_at": _now(),
            **fields,
        }
        self.log.append(entry)
        self._save("decision_log", self._log_row(entry))
        if entry.get("notifications"):
            self._save("notifications", self._notification_row(entry))
        return entry

    def persist_all(self) -> None:
        """Push everything to storage at once (used after an offline simulation)."""
        self._save("decision_log", [self._log_row(e) for e in self.log])
        self._save("notifications", [self._notification_row(e) for e in self.log if e.get("notifications")])
        self._save("groups", [self._group_row(g) for g in self.groups.values()])
        self._save("swm_tasks", [self._task_row(t) for t in self.swm_tasks.values()])
        self.save_site_status()

    # --------------------------------------------------------------- allocation

    def _fits(self, site: Site, slot_start: int, size: int, accept: set[str]) -> float | None:
        """Projected occupancy if `site` can take `size` people at `slot_start` and stay within `accept`, else None."""
        if not self.is_open(site, slot_start) or site.status in (RED, CLOSED):
            return None
        ratio = self.projected_ratio(site, slot_start, size)
        return ratio if self.status_for(ratio) in accept else None

    def _why_not(self, site: Site, slot_start: int, size: int) -> str:
        if site.closed:
            return f"{site.name} is closed"
        if not self.is_open(site, slot_start):
            return f"{site.name} is not open at {to_hhmm(slot_start)}"
        if site.status == RED:
            return f"{site.name} is RED right now ({pct(site.occupancy)} full)"
        ratio = self.projected_ratio(site, slot_start, size)
        return f"{site.name} would reach {pct(ratio)} of capacity ({self.status_for(ratio)}) at {to_hhmm(slot_start)}"

    def _find_alternative(self, origin: Site, slot_start: int, size: int, exclude: set[str], accept: set[str]):
        """Cheapest (site, slot) that keeps the group within `accept`.

        Cost is walking distance plus a fixed penalty per slot of delay, so a
        nearby site now beats the same site an hour later.
        """
        options = []
        for site in self.sites.values():
            if site.id in exclude:
                continue
            km = distance_km(origin.config, site.config)
            if km > self.rules["max_reroute_distance_km"]:
                continue
            for shift in range(self.rules["max_slot_shift"] + 1):
                if site is origin and shift == 0:
                    continue
                start = slot_start + shift * self.slot
                if start >= self.day_end:
                    break
                options.append((km + shift * self.rules["slot_shift_penalty_km"], km, site, start))
        for _, km, site, start in sorted(options, key=lambda o: o[0]):
            ratio = self._fits(site, start, size, accept)
            if ratio is not None:
                return site, start, ratio, km
        return None

    def allocate(self, request: dict) -> dict:
        """Decide ALLOCATED / DIVERTED / REJECTED for one group request and log the reason."""
        size = request["group_size"]
        name = request.get("group_name") or f"Group of {size}"
        request_id = self._next_id("REQ")
        wanted = to_min(request["preferred_time"]) if request.get("preferred_time") else self.clock
        slot = self.slot_of(max(wanted, self.clock))
        requested = {"site_id": request.get("preferred_site_id"), "time": to_hhmm(slot), "group_size": size}
        decide = lambda decision, option, reason, origin=None: self._decision(  # noqa: E731
            decision, request_id, name, size, requested, option, reason, origin, request.get("requested_by"))

        if size > self.rules["max_group_size"]:
            return decide("REJECTED", None, f"Group of {size} is above the festival limit of "
                          f"{self.rules['max_group_size']} per group; please split into smaller groups.")
        if slot >= self.day_end:
            return decide("REJECTED", None, f"{to_hhmm(slot)} is after festival hours (ends {to_hhmm(self.day_end)}).")

        if request.get("preferred_site_id"):
            pref = self.site(request["preferred_site_id"])
        else:
            open_sites = [s for s in self.sites.values() if self.is_open(s, slot)]
            if not open_sites:
                return decide("REJECTED", None, f"No site is open at {to_hhmm(slot)}.")
            pref = min(open_sites, key=lambda s: self.projected_ratio(s, slot, size))
            requested.update(site_id=pref.id, auto_selected=True)

        ratio = self._fits(pref, slot, size, {GREEN})
        if ratio is not None:
            return decide("ALLOCATED", (pref, slot, ratio, 0.0),
                          f"{pref.name} stays GREEN at {pct(ratio)} of capacity after adding this group.")

        why = self._why_not(pref, slot, size)
        max_km = self.rules["max_reroute_distance_km"]
        alt = self._find_alternative(pref, slot, size, set(), {GREEN})
        if alt:
            return decide("DIVERTED", alt, f"{why}; {self._describe(alt)} stays GREEN.", pref)

        if self.rules["allow_amber_allocation"]:
            ratio = self._fits(pref, slot, size, {GREEN, AMBER})
            if ratio is not None:
                return decide("ALLOCATED", (pref, slot, ratio, 0.0),
                              f"No GREEN option within {max_km} km; {pref.name} stays AMBER at "
                              f"{pct(ratio)}, so the group is allocated with caution.")
            alt = self._find_alternative(pref, slot, size, set(), {GREEN, AMBER})
            if alt:
                return decide("DIVERTED", alt, f"{why}; no GREEN option nearby, {self._describe(alt)} stays AMBER.", pref)

        return decide("REJECTED", None, f"{why}; no site within {max_km} km over the next "
                      f"{self.rules['max_slot_shift']} slots can take {size} more people safely.")

    def _describe(self, option) -> str:
        site, slot, ratio, km = option
        return f"{site.name} at {to_hhmm(slot)} ({km:.1f} km away, {pct(ratio)} full)"

    def _decision(self, decision, request_id, name, size, requested, option, reason, origin=None,
                  requested_by=None) -> dict:
        group = assigned = None
        if option:
            site, slot, ratio, km = option
            group = Group(self._next_id("GRP"), name, size, site.id, slot, requested_by=requested_by)
            self.groups[group.id] = group
            assigned = {"site_id": site.id, "site_name": site.name, "time": to_hhmm(slot),
                        "projected_occupancy": round(ratio, 3), "distance_km": round(km, 2)}
            actions = [
                {"audience": "VOLUNTEER", "action": "EXPECT_GROUP", "site_id": site.id,
                 "group_id": group.id, "group_size": size, "time": to_hhmm(slot)},
                {"audience": "CITIZEN", "action": "GO_TO_ALTERNATE_SITE" if decision == "DIVERTED" else "PROCEED_TO_SITE",
                 "site_id": site.id, "time": to_hhmm(slot)},
            ]
            if decision == "DIVERTED":
                messages = notify("DIVERTED", group=name, site_from=origin.name, site=site.name, time=to_hhmm(slot))
            else:
                messages = notify("ALLOCATED", group=name, site=site.name, time=to_hhmm(slot))
        else:
            actions = [{"audience": "CITIZEN", "action": "RETRY_LATER"}]
            messages = notify("REJECTED", group=name)

        entry = self._log("ALLOCATION", decision=decision, request_id=request_id, requested_by=requested_by,
                          group=group.to_dict() if group else None, requested=requested, assigned=assigned,
                          reason=reason, actions=actions, notifications=messages)
        if group:
            self._save_group(group)
            if group.slot_start <= self.clock:
                self._arrive(group)
            self._refresh([group.site_id], trigger=f"allocation {request_id}")
        return entry

    # ----------------------------------------------------- crowd status & reroute

    def _arrive(self, group: Group) -> None:
        group.status, group.arrived_at = ARRIVED, self.clock
        self.sites[group.site_id].crowd += group.size
        self._save_group(group)

    def _leave(self, group: Group) -> None:
        group.status = LEFT
        site = self.sites[group.site_id]
        site.crowd = max(0, site.crowd - group.size)
        self._save_group(group)

    def _refresh(self, site_ids=None, trigger: str = "update") -> None:
        """Recompute status for sites, then react: reroute on RED, warn early, check bins."""
        for site_id in site_ids or list(self.sites):
            site = self.sites[site_id]
            new = CLOSED if site.closed else self.status_for(site.occupancy)
            if new != site.status:
                old, site.status = site.status, new
                self._log("STATUS_CHANGE", site_id=site.id, site_name=site.name, from_status=old, to_status=new,
                          occupancy=round(site.occupancy, 3), trigger=trigger,
                          reason=f"{site.name} is at {pct(site.occupancy)} of capacity "
                                 f"(GREEN < {pct(self.th['green_max'])}, RED > {pct(self.th['amber_max'])})."
                          if new != CLOSED else f"{site.name} was closed.",
                          actions=self._status_actions(site))
            if site.status in (RED, CLOSED) and self.rules["reroute_pending_on_red"]:
                self._reroute_pending(site)
            self._predict_crowd(site)
            self._check_waste(site)

    def _status_actions(self, site: Site) -> list[dict]:
        return {
            RED: [{"audience": "BMC_OFFICER", "action": "CROWD_CONTROL", "site_id": site.id, "priority": "HIGH"},
                  {"audience": "VOLUNTEER", "action": "STOP_NEW_ENTRY", "site_id": site.id}],
            CLOSED: [{"audience": "BMC_OFFICER", "action": "DISPERSE_CROWD", "site_id": site.id, "priority": "HIGH"}],
            AMBER: [{"audience": "VOLUNTEER", "action": "MONITOR_QUEUE", "site_id": site.id}],
            GREEN: [{"audience": "VOLUNTEER", "action": "RESUME_NORMAL_ENTRY", "site_id": site.id}],
        }[site.status]

    def _reroute_pending(self, site: Site) -> None:
        """Move groups that have not arrived yet away from a RED or closed site."""
        window_end = self.clock + self.rules["reroute_window_minutes"]
        affected = sorted(
            (g for g in self.groups.values()
             if g.status == PENDING and g.site_id == site.id and (site.closed or g.slot_start < window_end)),
            key=lambda g: g.slot_start,
        )
        for group in affected:
            alt = self._find_alternative(site, group.slot_start, group.size, {site.id}, {GREEN})
            if not alt and self.rules["allow_amber_allocation"]:
                alt = self._find_alternative(site, group.slot_start, group.size, {site.id}, {GREEN, AMBER})
            if alt:
                new_site, slot, ratio, km = alt
                old_time = group.slot_start
                group.site_id, group.slot_start = new_site.id, slot
                group.reroutes += 1
                self._log("REROUTE", decision="REROUTED", group=group.to_dict(),
                          from_site_id=site.id, to_site_id=new_site.id,
                          from_time=to_hhmm(old_time), to_time=to_hhmm(slot),
                          reason=f"{site.name} turned {site.status}; {self._describe(alt)}.",
                          actions=[
                              {"audience": "VOLUNTEER", "action": "REDIRECT_GROUP", "site_id": site.id,
                               "group_id": group.id, "to_site_id": new_site.id},
                              {"audience": "VOLUNTEER", "action": "EXPECT_GROUP", "site_id": new_site.id,
                               "group_id": group.id, "group_size": group.size, "time": to_hhmm(slot)},
                              {"audience": "CITIZEN", "action": "GO_TO_ALTERNATE_SITE", "site_id": new_site.id,
                               "time": to_hhmm(slot)},
                          ],
                          notifications=notify("REROUTED", group=group.name, site_from=site.name,
                                               site=new_site.name, time=to_hhmm(slot)))
            else:
                group.status = CANCELLED
                self._log("REROUTE", decision="REJECTED", group=group.to_dict(), from_site_id=site.id,
                          reason=f"{site.name} turned {site.status} and no site within "
                                 f"{self.rules['max_reroute_distance_km']} km can take {group.size} people "
                                 f"in the next {self.rules['max_slot_shift']} slots.",
                          actions=[{"audience": "CITIZEN", "action": "RETRY_LATER"},
                                   {"audience": "BMC_OFFICER", "action": "REVIEW_CANCELLED_GROUP", "group_id": group.id}],
                          notifications=notify("REJECTED", group=group.name))
            self._save_group(group)

    def crowd_trend(self, site: Site) -> float:
        """People per minute over the last TREND_WINDOW_MINUTES (positive = filling up).

        Least-squares slope over every reading in the window, so a single noisy
        report does not look like a stampede.
        """
        samples = site.samples
        if len(samples) < 3 or samples[-1][0] - samples[0][0] < TREND_WINDOW_MINUTES / 2:
            return 0.0
        mean_t = sum(t for t, _ in samples) / len(samples)
        mean_c = sum(c for _, c in samples) / len(samples)
        spread = sum((t - mean_t) ** 2 for t, _ in samples)
        return sum((t - mean_t) * (c - mean_c) for t, c in samples) / spread

    def _record_sample(self, site: Site) -> None:
        site.samples.append((self.clock, site.crowd))
        site.samples = [s for s in site.samples if self.clock - s[0] <= TREND_WINDOW_MINUTES]

    def _predict_crowd(self, site: Site) -> None:
        """Warn an AMBER site before it turns RED: current crowd + recent growth + groups due next slot."""
        if site.status != AMBER:
            return
        next_slot = self.slot_of(self.clock) + self.slot
        if next_slot >= self.day_end or (site.id, next_slot) in self._warned:
            return
        growth = max(self.crowd_trend(site), 0.0) * (next_slot - self.clock)
        due = self.pending_load(site.id, next_slot)
        ratio = (site.crowd + growth + due) / site.capacity
        if self.status_for(ratio) == RED:
            self._warned.add((site.id, next_slot))
            self._log("PREDICTIVE_WARNING", site_id=site.id, site_name=site.name, slot_time=to_hhmm(next_slot),
                      projected_occupancy=round(ratio, 3),
                      reason=f"{site.name} is {pct(site.occupancy)} full and growing by "
                             f"{self.crowd_trend(site) * 60:.0f} people/hour, with {due} booked for "
                             f"{to_hhmm(next_slot)}; projected {pct(ratio)} (RED) by then.",
                      actions=[{"audience": "BMC_OFFICER", "action": "PREPARE_CROWD_CONTROL", "site_id": site.id},
                               {"audience": "VOLUNTEER", "action": "HOLD_WALK_INS", "site_id": site.id}])

    # -------------------------------------------------------------------- waste

    def waste_forecast(self, site: Site) -> tuple[float, float]:
        """(kg, fill ratio) expected in the bins at the end of the forecast window."""
        horizon = self.waste["forecast_minutes"]
        due = sum(g.size for g in self.groups.values()
                  if g.status == PENDING and g.site_id == site.id and g.slot_start < self.clock + horizon)
        kg = site.waste_kg + (site.crowd + due) * self.rate_per_person_hour * horizon / 60
        return kg, kg / site.bin_capacity_kg

    def _open_task(self, site_id: str) -> dict | None:
        return next((t for t in self.swm_tasks.values() if t["site_id"] == site_id and t["status"] == "OPEN"), None)

    def _save_task(self, task: dict) -> None:
        self._save("swm_tasks", self._task_row(task))

    def _check_waste(self, site: Site) -> None:
        trigger = self.waste["pickup_trigger_fill"]
        fill_now = site.waste_kg / site.bin_capacity_kg
        forecast_kg, fill_next = self.waste_forecast(site)
        if max(fill_now, fill_next) < trigger or self._open_task(site.id):
            return
        priority = "URGENT" if fill_now >= 0.9 else "HIGH" if fill_next >= 1.0 else "NORMAL"
        horizon = self.waste["forecast_minutes"]
        breakdown = {kind: round(forecast_kg * rate / self.rate_per_person_hour, 1)
                     for kind, rate in self.waste["per_person_per_hour_kg"].items()}
        task = {
            "id": self._next_id("SWM"), "festival_id": self.id, "site_id": site.id, "site_name": site.name,
            "lat": site.config["lat"], "lng": site.config["lng"], "status": "OPEN", "priority": priority,
            "created_at": to_hhmm(self.clock), "created_minute": self.clock,
            "current_fill": round(fill_now, 3), "forecast_fill": round(fill_next, 3),
            "forecast_window_minutes": horizon, "expected_load_kg": round(forecast_kg, 1),
            "waste_breakdown_kg": breakdown,
            "reason": f"Bins at {pct(fill_now)} now, forecast {pct(fill_next)} within {horizon} min "
                      f"(pickup trigger {pct(trigger)}).",
        }
        self.swm_tasks[task["id"]] = task
        self._save_task(task)
        self._log("SWM_TASK", task_id=task["id"], site_id=site.id, site_name=site.name, priority=priority,
                  reason=task["reason"],
                  actions=[{"audience": "SWM_TEAM", "action": "PICKUP", "site_id": site.id, "task_id": task["id"],
                            "priority": priority, "expected_load_kg": task["expected_load_kg"],
                            "waste_breakdown_kg": breakdown}],
                  notifications=notify("SWM_TASK", site=site.name, fill=round(fill_next * 100)))

    def complete_task(self, task_id: str, collected_kg: float | None = None) -> dict:
        task = self.swm_tasks.get(task_id)
        if not task:
            raise NotFoundError(f"Unknown SWM task '{task_id}'")
        if task["status"] != "OPEN":
            raise ValueError(f"Task {task_id} is already {task['status']}")
        site = self.sites[task["site_id"]]
        collected = site.waste_kg if collected_kg is None else min(collected_kg, site.waste_kg)
        site.waste_kg -= collected
        task.update(status="COMPLETED", completed_at=to_hhmm(self.clock), collected_kg=round(collected, 1))
        self._save_task(task)
        self._log("SWM_TASK_COMPLETED", task_id=task_id, site_id=site.id, site_name=site.name,
                  collected_kg=task["collected_kg"],
                  reason=f"SWM team cleared {task['collected_kg']} kg; bins now at {pct(site.waste_kg / site.bin_capacity_kg)}.",
                  actions=[])
        self._refresh([site.id], trigger=f"pickup {task_id}")
        return task

    def swm_routes(self) -> list[dict]:
        """Group nearby open pickups into one collection route each (nearest-neighbour order)."""
        pending = sorted((t for t in self.swm_tasks.values() if t["status"] == "OPEN"),
                         key=lambda t: (PRIORITY_RANK[t["priority"]], -t["forecast_fill"]))
        routes = []
        while pending:
            seed = pending.pop(0)
            cluster = [t for t in pending if distance_km(seed, t) <= self.waste["route_cluster_km"]]
            pending = [t for t in pending if t not in cluster]
            ordered, rest, total = [seed], cluster, 0.0
            while rest:
                nearest = min(rest, key=lambda t: distance_km(ordered[-1], t))
                total += distance_km(ordered[-1], nearest)
                ordered.append(nearest)
                rest.remove(nearest)
            routes.append({
                "route_id": f"ROUTE-{len(routes) + 1}",
                "priority": seed["priority"],
                "distance_km": round(total, 2),
                "expected_load_kg": round(sum(t["expected_load_kg"] for t in ordered), 1),
                "stops": [{"task_id": t["id"], "site_id": t["site_id"], "site_name": t["site_name"],
                           "lat": t["lat"], "lng": t["lng"], "priority": t["priority"]} for t in ordered],
            })
        return routes

    # ------------------------------------------------------------------- inputs

    def report(self, report: dict) -> dict:
        """Apply a citizen or volunteer report. Volunteers are trusted more than citizens."""
        site = self.site(report["site_id"])
        reporter = report["reporter_type"]
        weight = self.rules[f"{reporter}_report_weight"]
        if report["kind"] == "crowd":
            if report.get("crowd_count") is not None:
                target = report["crowd_count"]
            else:
                target = LEVEL_FRACTION[report["crowd_level"]] * site.capacity
            before = site.crowd
            site.crowd = max(0, round(weight * target + (1 - weight) * before))
            effect = f"Crowd estimate {before} -> {site.crowd} ({pct(site.occupancy)}), report weight {weight}."
        else:
            before = site.waste_kg
            target = report["bin_fill_percent"] / 100 * site.bin_capacity_kg
            site.waste_kg = weight * target + (1 - weight) * before
            effect = (f"Bin estimate {pct(before / site.bin_capacity_kg)} -> "
                      f"{pct(site.waste_kg / site.bin_capacity_kg)}, report weight {weight}.")
        entry = self._log("REPORT", kind=report["kind"], site_id=site.id, site_name=site.name,
                          reporter_type=reporter, input=report, reason=effect, actions=[])
        self._refresh([site.id], trigger=f"{reporter} {report['kind']} report {entry['id']}")
        return entry

    def sensor(self, site_id: str, entries: int = 0, exits: int = 0) -> dict:
        """Simulated gate counters."""
        site = self.site(site_id)
        site.crowd = max(0, site.crowd + entries - exits)
        self._refresh([site.id], trigger="entry/exit counter")
        return self.site_view(site)

    def advance(self, minutes: int) -> None:
        """Move the simulated clock: groups arrive and leave, bins fill up."""
        target = min(self.clock + minutes, self.day_end)
        while self.clock < target:
            step = min(TICK_MINUTES, target - self.clock)
            self.clock += step
            for group in self.groups.values():
                if group.status == PENDING and group.slot_start <= self.clock:
                    self._arrive(group)
                elif group.status == ARRIVED and self.clock - group.arrived_at >= self.rules["visit_minutes"]:
                    self._leave(group)
            for site in self.sites.values():
                site.waste_kg += site.crowd * self.rate_per_person_hour * step / 60
                self._record_sample(site)
            self._refresh(trigger="clock")

    def close_site(self, site_id: str, reason: str = "Closed by officer") -> dict:
        site = self.site(site_id)
        if site.closed:
            raise ValueError(f"{site.name} is already closed")
        site.closed = True
        entry = self._log("SITE_CLOSED", site_id=site.id, site_name=site.name, reason=reason,
                          actions=[{"audience": "VOLUNTEER", "action": "STOP_NEW_ENTRY", "site_id": site.id}])
        self._refresh([site.id], trigger=f"site closed: {reason}")
        return entry

    def open_site(self, site_id: str, reason: str = "Reopened by officer") -> dict:
        site = self.site(site_id)
        if not site.closed:
            raise ValueError(f"{site.name} is already open")
        site.closed = False
        entry = self._log("SITE_REOPENED", site_id=site.id, site_name=site.name, reason=reason, actions=[])
        self._refresh([site.id], trigger=f"site reopened: {reason}")
        return entry

    # ------------------------------------------------------------------ what-if

    def what_if(self, scenario: dict) -> dict:
        """Run a scenario on a copy of the engine; the live engine is untouched."""
        storage, self.storage = self.storage, None
        try:
            sim = copy.deepcopy(self)
        finally:
            self.storage = storage
        start = len(sim.log)
        if scenario.get("at_time"):
            at = to_min(scenario["at_time"])
            if at > sim.clock:
                sim.advance(at - sim.clock)
        site = sim.site(scenario["site_id"])
        if scenario["action"] == "close_site":
            sim.close_site(site.id, "What-if scenario")
        elif scenario["action"] == "reopen_site":
            sim.open_site(site.id, "What-if scenario")
        elif scenario["action"] == "crowd_surge":
            site.crowd += scenario.get("extra_people", 0)
            sim._refresh([site.id], trigger="what-if crowd surge")
        if scenario.get("then_advance_minutes"):
            sim.advance(scenario["then_advance_minutes"])
        events = sim.log[start:]
        return {
            "scenario": scenario,
            "note": "Simulated on a copy; nothing changed on the live engine.",
            "summary": dict(Counter(e.get("decision") or e["type"] for e in events)),
            "events": events,
            "sites_after": [sim.site_view(s) for s in sim.sites.values()],
        }

    # -------------------------------------------------------------------- views

    def site_view(self, site: Site) -> dict:
        current = self.slot_of(self.clock)
        forecast_kg, forecast_fill = self.waste_forecast(site)
        task = self._open_task(site.id)
        return {
            "id": site.id, "name": site.name, "lat": site.config["lat"], "lng": site.config["lng"],
            "capacity": site.capacity, "facilities": site.config["facilities"],
            "hours": {"open": site.config.get("open") or self.profile["day"]["start"],
                      "close": site.config.get("close") or self.profile["day"]["end"]},
            "status": site.status, "closed": site.closed,
            "crowd": site.crowd, "occupancy": round(site.occupancy, 3),
            "trend_people_per_hour": round(self.crowd_trend(site) * 60),
            "pending_current_slot": self.pending_load(site.id, current),
            "pending_next_slot": self.pending_load(site.id, current + self.slot),
            "projected_next_slot_occupancy": round(self.projected_ratio(site, current + self.slot), 3),
            "waste": {
                "current_kg": round(site.waste_kg, 1), "bin_capacity_kg": site.bin_capacity_kg,
                "fill": round(site.waste_kg / site.bin_capacity_kg, 3),
                "forecast_kg": round(forecast_kg, 1), "forecast_fill": round(forecast_fill, 3),
                "open_task_id": task["id"] if task else None,
            },
        }

    def snapshot(self) -> dict:
        return {
            "festival_id": self.id, "festival_name": self.name, "sim_time": to_hhmm(self.clock),
            "day": self.profile["day"], "thresholds": self.th,
            "sites": [self.site_view(s) for s in self.sites.values()],
            "groups": dict(Counter(g.status for g in self.groups.values())),
            "open_swm_tasks": sum(t["status"] == "OPEN" for t in self.swm_tasks.values()),
            "log_entries": len(self.log),
        }
