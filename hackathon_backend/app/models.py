"""Request bodies for the API (responses are plain JSON dicts from the engine)."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .profiles import HHMM



class VolunteerAccessCode(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    access_code: str = Field(min_length=12, max_length=128)

    @model_validator(mode="after")
    def valid_email(self):
        self.email = self.email.strip().lower()
        if "@" not in self.email or "." not in self.email.rsplit("@", 1)[-1]:
            raise ValueError("Enter the email address associated with your volunteer code")
        self.access_code = self.access_code.strip()
        return self

class GroupRequest(BaseModel):
    group_name: str | None = Field(None, examples=["Patil family"])
    group_size: int = Field(gt=0, examples=[25])
    preferred_site_id: str | None = Field(None, examples=["lalbaugcha_raja"],
                                          description="Leave empty to let the engine pick the least crowded site")
    preferred_time: str | None = Field(None, pattern=HHMM, examples=["19:00"],
                                       description="Defaults to now (simulated clock)")


class Report(BaseModel):
    site_id: str = Field(examples=["lalbaugcha_raja"])
    reporter_type: Literal["citizen", "volunteer"]
    kind: Literal["crowd", "waste"]
    crowd_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] | None = None
    crowd_count: int | None = Field(None, ge=0, description="Head count, if the reporter has one")
    bin_fill_percent: float | None = Field(None, ge=0, le=150)
    note: str | None = None

    @model_validator(mode="after")
    def has_reading(self):
        if self.kind == "crowd" and self.crowd_level is None and self.crowd_count is None:
            raise ValueError("crowd reports need crowd_level or crowd_count")
        if self.kind == "waste" and self.bin_fill_percent is None:
            raise ValueError("waste reports need bin_fill_percent")
        return self


class FieldReport(BaseModel):
    """One volunteer form: any mix of crowd reading, bin level, gate counts and remarks."""
    site_id: str = Field(examples=["lalbaugcha_raja"])
    crowd_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] | None = Field(None, examples=["HIGH"])
    crowd_count: int | None = Field(None, ge=0, description="Head count, if known (overrides crowd_level)")
    waste_level_percent: float | None = Field(None, ge=0, le=150, examples=[70])
    entries: int = Field(0, ge=0, examples=[120])
    exits: int = Field(0, ge=0, examples=[40])
    remarks: str | None = Field(None, examples=["Queue spilling onto the main road"])

    @model_validator(mode="after")
    def has_reading(self):
        if (self.crowd_level is None and self.crowd_count is None and self.waste_level_percent is None
                and not self.entries and not self.exits):
            raise ValueError("send at least one of crowd_level, crowd_count, waste_level_percent, entries, exits")
        return self


class SensorUpdate(BaseModel):
    site_id: str
    entries: int = Field(0, ge=0)
    exits: int = Field(0, ge=0)


class AdvanceClock(BaseModel):
    minutes: int = Field(gt=0, le=1440, examples=[30])


class SiteAction(BaseModel):
    reason: str = "Instruction from BMC officer"


class CompleteTask(BaseModel):
    collected_kg: float | None = Field(None, ge=0, description="Defaults to emptying the bins")


class WhatIf(BaseModel):
    action: Literal["close_site", "reopen_site", "crowd_surge"]
    site_id: str = Field(examples=["lalbaugcha_raja"])
    at_time: str | None = Field(None, pattern=HHMM, examples=["21:00"],
                                description="Fast-forward the copy to this time first")
    extra_people: int | None = Field(0, ge=0, description="For crowd_surge")
    then_advance_minutes: int | None = Field(0, ge=0, le=1440)

    @field_validator("extra_people", "then_advance_minutes", "at_time", mode="before")
    @classmethod
    def blank_is_unset(cls, value):
        # Form fields left empty arrive as null or "" (or NaN, which JSON sends as null).
        return None if value in ("", None) else value

    @model_validator(mode="after")
    def fill_defaults(self):
        self.extra_people = self.extra_people or 0
        self.then_advance_minutes = self.then_advance_minutes or 0
        return self


class SimulateRequest(BaseModel):
    events: int = Field(75, ge=50, le=100, description="Requests + reports in the day")
    seed: int = 42
    replace_live: bool = Field(False, description="Make the simulated day the live state shown on the dashboard")

