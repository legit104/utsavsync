"""Festival profiles: the configuration that makes the engine reusable.

A profile describes one festival (sites, capacity, timings, thresholds, bins,
waste types and rules). Adding a festival means adding a JSON file here or
POSTing it to /festivals, never changing code.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles"
HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class Bins(BaseModel):
    count: int = Field(gt=0)
    capacity_kg: float = Field(gt=0, description="Capacity of one bin in kg")


class SiteConfig(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    capacity: int = Field(gt=0, description="Safe number of people on site at once")
    open: str | None = Field(None, pattern=HHMM, description="Defaults to the festival start")
    close: str | None = Field(None, pattern=HHMM, description="Defaults to the festival end")
    facilities: list[str] = []
    bins: Bins
    popularity: float = Field(1.0, gt=0, description="Relative demand, used by the simulator")


class Day(BaseModel):
    start: str = Field(pattern=HHMM)
    end: str = Field(pattern=HHMM)
    slot_minutes: int = Field(gt=0, le=240)

    @model_validator(mode="after")
    def start_before_end(self):
        if self.start >= self.end:
            raise ValueError("day.start must be before day.end (same calendar day)")
        return self


class Thresholds(BaseModel):
    green_max: float = Field(0.60, gt=0, description="Occupancy below this is GREEN")
    amber_max: float = Field(0.85, gt=0, description="Occupancy up to this is AMBER, above is RED")

    @model_validator(mode="after")
    def ordered(self):
        if self.green_max >= self.amber_max:
            raise ValueError("thresholds.green_max must be below thresholds.amber_max")
        return self


class Rules(BaseModel):
    max_group_size: int = Field(50, gt=0)
    visit_minutes: int = Field(45, gt=0, description="How long a group stays on site")
    allow_amber_allocation: bool = True
    reroute_pending_on_red: bool = True
    reroute_window_minutes: int = Field(120, ge=0, description="Reroute pending groups due within this window when a site turns RED")
    max_reroute_distance_km: float = Field(5.0, gt=0)
    max_slot_shift: int = Field(2, ge=0, description="How many slots later an alternative may be")
    slot_shift_penalty_km: float = Field(1.5, ge=0, description="A one-slot delay costs the same as walking this far")
    volunteer_report_weight: float = Field(0.8, ge=0, le=1)
    citizen_report_weight: float = Field(0.4, ge=0, le=1)


class Waste(BaseModel):
    per_person_per_hour_kg: dict[str, float] = Field(min_length=1, description="Waste generated per person per hour, by type")
    pickup_trigger_fill: float = Field(0.75, gt=0, le=1.5)
    forecast_minutes: int = Field(60, gt=0)
    route_cluster_km: float = Field(2.0, gt=0, description="Pickups closer than this are grouped into one SWM route")


class Simulation(BaseModel):
    peak_time: str | None = Field(None, pattern=HHMM)
    peak_occupancy: float = Field(0.7, gt=0)
    spread_hours: float = Field(3.0, gt=0)


class FestivalProfile(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str
    description: str = ""
    day: Day
    thresholds: Thresholds = Thresholds()
    rules: Rules = Rules()
    waste: Waste
    simulation: Simulation = Simulation()
    sites: list[SiteConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_site_ids(self):
        ids = [s.id for s in self.sites]
        if len(ids) != len(set(ids)):
            raise ValueError("site ids must be unique within a festival")
        return self


def load_profiles(directory: Path = PROFILES_DIR) -> dict[str, dict]:
    profiles = {}
    for path in sorted(directory.glob("*.json")):
        profile = FestivalProfile.model_validate_json(path.read_text(encoding="utf-8"))
        profiles[profile.id] = profile.model_dump()
    return profiles


def save_profile(profile: dict, directory: Path = PROFILES_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{profile['id']}.json"
    path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
