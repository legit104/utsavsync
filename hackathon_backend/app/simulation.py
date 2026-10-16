"""Festival day simulation and the scripted live rerouting demo.

Run from the command line:  python -m app.simulation --events 80
"""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter
from pathlib import Path

from .engine import ARRIVED, CLOSED, RED, FestivalEngine, distance_km, to_hhmm, to_min
from .profiles import load_profiles

SENSOR_EVERY_MINUTES = 10
SWM_RESPONSE_MINUTES = 45
DEMO_GROUP_SIZES = (10, 15, 20)


def baseline_crowd(engine: FestivalEngine, site, minute: int) -> float:
    """Walk-in crowd for a site: a bell curve around the festival's peak time."""
    sim = engine.profile.get("simulation") or {}
    peak = to_min(sim["peak_time"]) if sim.get("peak_time") else (engine.day_start + engine.day_end) // 2
    spread = sim.get("spread_hours", 3.0) * 60
    peak_people = sim.get("peak_occupancy", 0.7) * site.config.get("popularity", 1.0) * site.capacity
    return peak_people * math.exp(-(((minute - peak) / spread) ** 2) / 2)


def feed_sensors(engine: FestivalEngine, rng: random.Random) -> None:
    """Simulated gate counters: nudge each site's crowd toward walk-ins + groups on site."""
    for site in engine.sites.values():
        if site.closed:
            continue
        on_site = sum(g.size for g in engine.groups.values() if g.status == ARRIVED and g.site_id == site.id)
        target = baseline_crowd(engine, site, engine.clock) + on_site
        delta = round((target - site.crowd) * rng.uniform(0.8, 1.1))
        engine.sensor(site.id, entries=max(delta, 0), exits=max(-delta, 0))


def complete_due_tasks(engine: FestivalEngine) -> None:
    """Pretend SWM teams finish each pickup a fixed time after it is raised."""
    for task in list(engine.swm_tasks.values()):
        if task["status"] == "OPEN" and engine.clock - task["created_minute"] >= SWM_RESPONSE_MINUTES:
            engine.complete_task(task["id"])


def _demo_site(engine: FestivalEngine):
    """Quietest open site that has a neighbour close enough to reroute to."""
    max_km = engine.rules["max_reroute_distance_km"]
    candidates = [
        s for s in engine.sites.values()
        if s.status not in (RED, CLOSED)
        and any(o is not s and not o.closed and distance_km(s.config, o.config) <= max_km for o in engine.sites.values())
    ]
    if not candidates:
        raise ValueError("No open site has a neighbour within reroute distance.")
    return min(candidates, key=lambda s: s.occupancy)


def run_reroute_demo(engine: FestivalEngine, site_id: str | None = None) -> dict:
    """Book groups into a site's next slot, then a volunteer reports it CRITICAL.

    The engine turns the site RED and moves the booked groups automatically:
    the "live rerouting triggered by a crowd status change" deliverable.
    """
    site = engine.site(site_id) if site_id else _demo_site(engine)
    next_slot = engine.slot_of(engine.clock) + engine.slot
    if next_slot >= engine.day_end:
        raise ValueError("Not enough festival time left for the demo; reset the festival first.")
    start = len(engine.log)
    bookings = [
        engine.allocate({"group_name": f"Demo group {n + 1}", "group_size": size,
                         "preferred_site_id": site.id, "preferred_time": to_hhmm(next_slot)})
        for n, size in enumerate(DEMO_GROUP_SIZES)
    ]
    engine.report({"site_id": site.id, "reporter_type": "volunteer", "kind": "crowd",
                   "crowd_level": "CRITICAL", "note": "Demo: sudden surge at the entrance"})
    events = engine.log[start:]
    return {
        "site_id": site.id,
        "site_name": site.name,
        "status_after": site.status,
        "bookings": [{"group": b["group"], "decision": b["decision"], "assigned": b["assigned"]} for b in bookings],
        "reroutes": [e for e in events if e["type"] == "REROUTE"],
        "events": events,
    }


def simulate_day(profile: dict, events: int = 75, seed: int = 42) -> tuple[FestivalEngine, dict]:
    """Play a festival day of `events` requests and reports, including one scripted surge."""
    rng = random.Random(seed)
    engine = FestivalEngine(profile)
    sites = list(engine.sites.values())
    weights = [s.config.get("popularity", 1.0) for s in sites]
    demo_inputs = len(DEMO_GROUP_SIZES) + 1
    times = sorted(rng.randrange(engine.day_start, engine.day_end - engine.slot) for _ in range(events - demo_inputs))
    surge_at = int(len(times) * 0.4)
    next_sensor = engine.day_start
    inputs = Counter()

    def run_until(minute: int) -> None:
        nonlocal next_sensor
        while engine.clock < minute:
            step_to = min(minute, next_sensor)
            if step_to > engine.clock:
                engine.advance(step_to - engine.clock)
            if engine.clock >= next_sensor:
                feed_sensors(engine, rng)
                complete_due_tasks(engine)
                next_sensor += SENSOR_EVERY_MINUTES

    for i, minute in enumerate(times):
        run_until(minute)
        if i == surge_at:
            try:
                run_reroute_demo(engine)
                inputs["group_requests"] += len(DEMO_GROUP_SIZES)
                inputs["crowd_reports"] += 1
            except ValueError:
                pass
        site = rng.choices(sites, weights)[0]
        roll = rng.random()
        if roll < 0.6:
            shift = rng.choice([0, 1, 1, 2]) * engine.slot
            engine.allocate({
                "group_name": f"Group {i + 1}",
                "group_size": rng.randint(5, engine.rules["max_group_size"]),
                "preferred_site_id": site.id,
                "preferred_time": to_hhmm(min(engine.clock + shift, engine.day_end - 1)),
            })
            inputs["group_requests"] += 1
        elif roll < 0.85:
            seen = site.occupancy + rng.uniform(-0.1, 0.15)
            level = "LOW" if seen < 0.45 else "MEDIUM" if seen < 0.78 else "HIGH" if seen < 1.0 else "CRITICAL"
            engine.report({"site_id": site.id, "reporter_type": rng.choice(["citizen", "volunteer"]),
                           "kind": "crowd", "crowd_level": level})
            inputs["crowd_reports"] += 1
        else:
            fill = site.waste_kg / site.bin_capacity_kg + rng.uniform(0, 0.2)
            engine.report({"site_id": site.id, "reporter_type": rng.choice(["citizen", "volunteer"]),
                           "kind": "waste", "bin_fill_percent": round(min(fill, 1.5) * 100, 1)})
            inputs["waste_reports"] += 1

    types = Counter(e["type"] for e in engine.log)
    reroutes = Counter(e["decision"] for e in engine.log if e["type"] == "REROUTE")
    summary = {
        "festival_id": engine.id,
        "festival_name": engine.name,
        "seed": seed,
        "simulated_until": to_hhmm(engine.clock),
        "inputs": dict(inputs),
        "total_inputs": sum(inputs.values()),
        "allocation_decisions": dict(Counter(e["decision"] for e in engine.log if e["type"] == "ALLOCATION")),
        "reroutes": {"rerouted": reroutes["REROUTED"], "cancelled": reroutes["REJECTED"]},
        "status_changes": types["STATUS_CHANGE"],
        "predictive_warnings": types["PREDICTIVE_WARNING"],
        "swm_tasks_created": types["SWM_TASK"],
        "swm_tasks_completed": types["SWM_TASK_COMPLETED"],
        "decision_log_entries": len(engine.log),
    }
    return engine, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate a festival day for each profile.")
    parser.add_argument("festivals", nargs="*", help="Profile ids (default: all)")
    parser.add_argument("--events", type=int, default=75, help="Requests + reports per festival (50-100)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=Path("output"))
    args = parser.parse_args()

    profiles = load_profiles()
    args.out.mkdir(parents=True, exist_ok=True)
    for festival_id in args.festivals or list(profiles):
        engine, summary = simulate_day(profiles[festival_id], args.events, args.seed)
        (args.out / f"{festival_id}_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        (args.out / f"{festival_id}_decision_log.json").write_text(
            json.dumps(engine.log, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(summary, indent=2))
    print(f"Decision logs written to {args.out.resolve()}")


if __name__ == "__main__":
    main()
