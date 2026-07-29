"""Domain types for the constraint planner.

Everything here is timezone-aware and integer-cents. Validation lives at this
boundary on purpose: a naive datetime or a city-less in-person meeting should
fail where a human can read the message, not four frames deep in the solver.
"""
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Mode = Literal["in_person", "virtual"]
Severity = Literal["low", "medium", "high"]


def _require_aware(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value


class Meeting(BaseModel):
    id: str = ""
    title: str
    city: str | None = None      # IATA code; required when in person
    mode: Mode
    starts_at: datetime
    ends_at: datetime
    # False => binding. For an in-person meeting that means presence is
    # required; for a virtual one, that the call may not be taken from the air.
    # One flag, both modes, defaulting to binding.
    flexible: bool = False

    @model_validator(mode="after")
    def _check(self) -> "Meeting":
        _require_aware(self.starts_at, "starts_at")
        _require_aware(self.ends_at, "ends_at")
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        if self.mode == "in_person" and not self.city:
            raise ValueError("an in-person meeting needs a city")
        return self


class Violation(BaseModel):
    kind: str   # presence | no_fly | budget | policy | red_eye | connections | no_flights
    severity: Literal["hard", "soft"]
    message: str
    meeting_id: str | None = None


class TripIntent(BaseModel):
    origin_city: str
    meetings: list[Meeting] = Field(default_factory=list)
    budget_cents: int | None = None
    preferences: dict = Field(default_factory=dict)
    policy_rules: dict = Field(default_factory=dict)

    def binding_meetings(self) -> list[Meeting]:
        return [m for m in self.meetings if not m.flexible]

    def in_person(self) -> list[Meeting]:
        return [m for m in self.binding_meetings() if m.mode == "in_person"]

    def virtual(self) -> list[Meeting]:
        return [m for m in self.binding_meetings() if m.mode == "virtual"]


class Leg(BaseModel):
    origin: str
    destination: str
    depart_at: datetime
    arrive_at: datetime
    airline: str
    fare_class: str
    price_cents: int
    stops: int = 0
    # Duffel offers on aggregator content go stale within seconds, so this is a
    # hint for repricing, never something to book from directly.
    offer_id: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "Leg":
        _require_aware(self.depart_at, "depart_at")
        _require_aware(self.arrive_at, "arrive_at")
        if self.arrive_at <= self.depart_at:
            raise ValueError("arrive_at must be after depart_at")
        return self

    @property
    def duration(self) -> timedelta:
        return self.arrive_at - self.depart_at


class Itinerary(BaseModel):
    id: str = ""
    legs: list[Leg]
    total_price_cents: int = 0
    soft_violations: list[Violation] = Field(default_factory=list)

    @classmethod
    def from_legs(cls, legs: list[Leg]) -> "Itinerary":
        return cls(legs=legs, total_price_cents=sum(leg.price_cents for leg in legs))


class PlanResult(BaseModel):
    """Either a feasible set, or the reason there isn't one.

    Never both, and never an unexplained empty list — "no results" is the one
    answer a traveler can do nothing with.
    """
    itineraries: list[Itinerary] = Field(default_factory=list)
    binding_constraint: Violation | None = None
    relaxation: str | None = None


class RiskFactor(BaseModel):
    code: str
    detail: str


class RiskAssessment(BaseModel):
    severity: Severity = "low"
    advisory: str = ""
    recommendations: list[str] = Field(default_factory=list)
    factors: list[RiskFactor] = Field(default_factory=list)


class Ranking(BaseModel):
    itinerary_id: str
    rank: int
    rationale: str
    concerns: list[str] = Field(default_factory=list)
