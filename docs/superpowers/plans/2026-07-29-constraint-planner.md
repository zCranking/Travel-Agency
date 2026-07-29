# Constraint Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the "chat wrapper over flight search" with a constraint planner — the traveler states the meetings they must make, code enumerates every itinerary that actually satisfies them, and a model ranks those, explains the trade-offs, and assesses duty-of-care risk.

**Architecture:** Three stages. `interpret` (AI) turns prose into a *draft* `TripIntent` the traveler confirms. `solve` (pure Python, search injected) enumerates feasible itineraries against pluggable hard/soft checkers, or names the binding constraint when nothing is feasible. `judge` + `risk` (AI) rank and explain over the solver's output only. Booking goes through the existing `issue_ticket()` after a mandatory reprice.

**Tech Stack:** Same as existing — Python 3.13 / FastAPI / pydantic / LangChain `ChatAnthropic` (`claude-sonnet-5`) / Supabase, Next.js App Router + Tailwind. No new dependencies (`zoneinfo` is stdlib).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-29-constraint-planner-design.md` — implements it in full.
- **The invariant:** the AI never emits an itinerary that code has not validated, and code never guesses at intent. Any model output naming an id must be validated against ids the server issued.
- Every AI layer has a deterministic fallback. A misbehaving model degrades output quality; it never 500s an endpoint.
- Booking stays behind `issue_ticket()` (`api/travel/ticketing.py`). Do not add a second path that writes `status='booked'`.
- Money is `int` cents end to end; any decimal string from a supplier goes through `Decimal`, never `float`.
- All meeting/flight times are timezone-aware `datetime`. Never compare a naive datetime to an aware one, and never compare dates where instants are meant.
- `api/` remains the only place that calls Claude/Duffel/Voyage.
- Frontend matches the existing palette and type roles (`--color-ink/paper/amber/teal/coral/slate/mute/line`, `font-display`/`font-sans`/`font-mono`) and reuses `AppShell`/`Button`/`Badge`. No new visual direction.
- Run from repo root: `cd api && .venv/Scripts/python.exe -m pytest` and `cd api && .venv/Scripts/python.exe -m ruff check .`. Both must be clean at the end of every task.
- Every task ends with its own commit and a clean `git status`.

---

### Task 1: Migration — meetings, itineraries, trip/employee columns

Also fixes a real collision: `supabase/migrations/` currently has **two** files numbered `00000000000005`. Alphabetically `employee_self_update` sorts before `traveler_profile`, but it grants `update (name, traveler_profile)` on a column `traveler_profile` creates — so a fresh `db push` / `db reset` fails today. The live project applied them in the right order (its history is timestamp-versioned, checked), so renaming the local file is safe and affects only fresh setups.

**Files:**
- Rename: `supabase/migrations/00000000000005_employee_self_update.sql` → `00000000000006_employee_self_update.sql`
- Create: `supabase/migrations/00000000000007_planning.sql`

**Interfaces:**
- Consumes: nothing.
- Produces: tables `meetings`, `itineraries`; columns `trips.origin_city`, `trips.budget_cents`, `employees.travel_preferences`. Tasks 6, 8 and 9 read/write these.

- [ ] **Step 1: Rename the colliding migration**

```bash
git mv supabase/migrations/00000000000005_employee_self_update.sql \
       supabase/migrations/00000000000006_employee_self_update.sql
```

- [ ] **Step 2: Write the new migration**

Create `supabase/migrations/00000000000007_planning.sql`:

```sql
-- Constraint planner: the traveler states meetings, the solver produces
-- itineraries. Meetings live in their own table rather than a blob on `trips`
-- specifically so a future calendar connector writes rows here and nothing
-- else changes.

create table meetings (
    id uuid primary key default gen_random_uuid(),
    trip_id uuid not null references trips(id) on delete cascade,
    title text not null,
    city text,                 -- IATA code; required for in-person
    mode text not null check (mode in ('in_person', 'virtual')),
    starts_at timestamptz not null,
    ends_at timestamptz not null,
    -- false => binding. The solver may not violate a binding meeting: an
    -- itinerary that would is infeasible, not merely worse. Defaults to
    -- binding -- fail closed, same as the fare-class and token checks.
    flexible boolean not null default false,
    created_at timestamptz not null default now(),
    constraint in_person_needs_a_city check (mode = 'virtual' or city is not null),
    constraint meeting_ends_after_it_starts check (ends_at > starts_at)
);

-- Itineraries are persisted, not held client-side, for the same reason Duffel
-- offers are cached server-side: selection must reference something the server
-- issued. A plan handed back by a client (or a model) that we never produced
-- gets refused, exactly like an unknown offer id.
create table itineraries (
    id uuid primary key default gen_random_uuid(),
    trip_id uuid not null references trips(id) on delete cascade,
    legs jsonb not null,
    total_price_cents int not null,
    soft_violations jsonb not null default '[]',
    rank int,
    rationale text,
    concerns jsonb not null default '[]',
    risk jsonb,
    selected boolean not null default false,
    created_at timestamptz not null default now()
);

alter table trips add column origin_city text;
-- Soft, not hard: over budget is a flagged plan, never a hidden one.
alter table trips add column budget_cents int;

-- {avoid_red_eyes: bool, max_connections: int, earliest_departure: "HH:MM",
--  latest_arrival: "HH:MM"} -- all soft, all optional.
alter table employees add column travel_preferences jsonb;

-- Read only through the backend (service role), like `bookings`: RLS on with
-- no policy is default-deny for anon/authenticated, rather than inventing
-- access rules nothing needs yet.
alter table meetings enable row level security;
alter table itineraries enable row level security;

create index meetings_trip_id_idx on meetings (trip_id);
create index itineraries_trip_id_idx on itineraries (trip_id);
```

- [ ] **Step 3: Apply it to the live project**

Apply via the Supabase MCP `apply_migration` tool against project `hjkuoqswzyzouyucihuz`, migration name `planning`, with the SQL body above (everything after the leading comment). Then verify:

```
execute_sql: select column_name from information_schema.columns
             where table_name = 'meetings' order by column_name;
```
Expected: `city, created_at, ends_at, flexible, id, mode, starts_at, title, trip_id`.

- [ ] **Step 4: Check advisors**

Run the Supabase MCP `get_advisors` tool with `type: "security"`. Expected: no new RLS-disabled findings for `meetings` or `itineraries`.

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/
git commit -m "feat(db): meetings + itineraries tables for the constraint planner

Also renumbers employee_self_update to 0006 -- it collided with
traveler_profile at 0005 and sorted ahead of the column it grants on, so a
fresh db reset failed."
```

---

### Task 2: `FlightOption` gains departure/arrival instants

A solver cannot reason about a date. `FlightOption` carries `depart_date` and no clock; add instants with defaults so every existing caller and test keeps working.

**Files:**
- Modify: `api/travel/models.py`
- Test: `api/tests/test_duffel_client.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `FlightOption.depart_at: str`, `.arrive_at: str` (ISO 8601 **with** UTC offset, `""` when unknown), `.stops: int`. Tasks 3, 5 and 6 read these.

- [ ] **Step 1: Write the failing test**

Add to `api/tests/test_duffel_client.py`:

```python
def test_flight_option_carries_instants_and_defaults_to_blank():
    from travel.models import FlightOption

    bare = FlightOption(
        id="x", airline="United", fare_class="economy", origin="SFO",
        destination="ORD", depart_date="2026-09-01", price_cents=31000,
    )
    assert (bare.depart_at, bare.arrive_at, bare.stops) == ("", "", 0)

    timed = FlightOption(
        id="x", airline="United", fare_class="economy", origin="SFO",
        destination="ORD", depart_date="2026-09-01", price_cents=31000,
        depart_at="2026-09-01T07:30:00-07:00",
        arrive_at="2026-09-01T13:45:00-05:00",
        stops=1,
    )
    assert timed.depart_at.endswith("-07:00")
    assert timed.stops == 1
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd api && .venv/Scripts/python.exe -m pytest tests/test_duffel_client.py::test_flight_option_carries_instants_and_defaults_to_blank -v`
Expected: FAIL — pydantic rejects the unknown fields `depart_at`/`arrive_at`/`stops`.

- [ ] **Step 3: Add the fields**

In `api/travel/models.py`, inside `FlightOption`, after `currency`:

```python
    # ISO 8601 *with* offset. A solver reasoning about "land before the 2pm
    # meeting" needs an instant, not a date; the offset is what makes a
    # Denver arrival and a Chicago meeting comparable. Blank when the source
    # doesn't supply times (older mock fixtures, seeded rows).
    depart_at: str = ""
    arrive_at: str = ""
    stops: int = 0
```

- [ ] **Step 4: Run the full suite**

Run: `cd api && .venv/Scripts/python.exe -m pytest`
Expected: all pass — defaults keep every existing construction valid.

- [ ] **Step 5: Commit**

```bash
git add api/travel/models.py api/tests/test_duffel_client.py
git commit -m "feat(travel): carry departure/arrival instants and stops on FlightOption"
```

---

### Task 3: Real and mock clients populate the instants

**Files:**
- Modify: `api/travel/duffel_client.py`
- Test: `api/tests/test_duffel_real_client.py`, `api/tests/test_duffel_client.py`

**Interfaces:**
- Consumes: `FlightOption.depart_at/.arrive_at/.stops` (Task 2).
- Produces: `_leg_times(offer: dict) -> tuple[str, str, int]` in `api/travel/duffel_client.py`. Nothing outside the module calls it; the contract that matters is that both clients now return populated instants.

- [ ] **Step 1: Write the failing tests**

Add to `api/tests/test_duffel_real_client.py`:

```python
@patch("travel.duffel_client.httpx.post")
def test_search_flights_attaches_airport_timezones_to_segment_times(mock_post):
    """Duffel reports segment times as naive local strings and the zone on the
    airport. Without stitching them the solver would compare a Chicago clock
    to a San Francisco one."""
    _ok(mock_post, {"data": {
        "passengers": [{"id": "pas_1"}],
        "offers": [{
            "id": "off_1",
            "total_amount": "310.00",
            "total_currency": "USD",
            "owner": {"name": "United"},
            "slices": [{"segments": [
                {
                    "departing_at": "2026-09-01T07:30:00",
                    "arriving_at": "2026-09-01T11:20:00",
                    "origin": {"iata_code": "SFO", "time_zone": "America/Los_Angeles"},
                    "destination": {"iata_code": "DEN", "time_zone": "America/Denver"},
                    "passengers": [{"cabin_class": "economy"}],
                },
                {
                    "departing_at": "2026-09-01T12:40:00",
                    "arriving_at": "2026-09-01T16:05:00",
                    "origin": {"iata_code": "DEN", "time_zone": "America/Denver"},
                    "destination": {"iata_code": "ORD", "time_zone": "America/Chicago"},
                    "passengers": [{"cabin_class": "economy"}],
                },
            ]}],
        }],
    }})

    option = _client().search_flights("SFO", "ORD", "2026-09-01")[0]

    assert option.depart_at == "2026-09-01T07:30:00-07:00"   # first segment out
    assert option.arrive_at == "2026-09-01T16:05:00-05:00"   # last segment in
    assert option.stops == 1                                  # two segments, one stop


@patch("travel.duffel_client.httpx.post")
def test_search_flights_survives_an_offer_with_no_segment_times(mock_post):
    """Blank instants, not a crash: the offer is still bookable, it just can't
    participate in constraint solving."""
    _ok(mock_post, {"data": {
        "passengers": [{"id": "pas_1"}],
        "offers": [{
            "id": "off_1", "total_amount": "310.00", "total_currency": "USD",
            "owner": {"name": "United"}, "slices": [],
        }],
    }})

    option = _client().search_flights("SFO", "ORD", "2026-09-01")[0]

    assert (option.depart_at, option.arrive_at, option.stops) == ("", "", 0)
```

Add to `api/tests/test_duffel_client.py`:

```python
def test_mock_flights_have_usable_instants():
    """The planner has to demo and test with no Duffel token, so the mock
    must supply times the solver can reason about."""
    from datetime import datetime

    from travel.duffel_client import MockDuffelClient

    options = MockDuffelClient().search_flights("SFO", "ORD", "2026-09-01")

    for option in options:
        depart = datetime.fromisoformat(option.depart_at)
        arrive = datetime.fromisoformat(option.arrive_at)
        assert depart.tzinfo is not None and arrive.tzinfo is not None
        assert arrive > depart
        assert depart.date().isoformat() == "2026-09-01"

    # spread across the day, so a presence window can actually discriminate
    assert len({o.depart_at for o in options}) == len(options)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd api && .venv/Scripts/python.exe -m pytest tests/test_duffel_real_client.py -k timezones tests/test_duffel_client.py -k instants -v`
Expected: FAIL — `depart_at` is `""`.

- [ ] **Step 3: Implement `_leg_times` and wire it into `RealDuffelClient`**

In `api/travel/duffel_client.py`, add to the imports:

```python
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
```

Add next to `_cabin_class`:

```python
def _at(segment: dict, which: str) -> str:
    """Stitch a Duffel segment time to its airport's zone.

    Duffel sends `departing_at` as a naive local string ("2026-09-01T07:30:00")
    and puts the IANA zone on the airport object. Neither half is usable
    alone: comparing a Chicago wall clock to a Denver one is how you plan a
    trip that misses the meeting.
    """
    endpoint = "origin" if which == "departing_at" else "destination"
    zone = ZoneInfo(segment[endpoint]["time_zone"])
    return datetime.fromisoformat(segment[which]).replace(tzinfo=zone).isoformat()


def _leg_times(offer: dict) -> tuple[str, str, int]:
    """(depart_at, arrive_at, stops) across the whole journey.

    Returns blanks rather than raising on a malformed offer — an offer with no
    readable schedule is still bookable through the chat path, it just can't
    take part in constraint solving. Failing the search outright would be a
    worse trade than degrading one option.
    """
    try:
        segments = offer["slices"][0]["segments"]
        return (
            _at(segments[0], "departing_at"),
            _at(segments[-1], "arriving_at"),
            len(segments) - 1,
        )
    except (KeyError, IndexError, TypeError, ValueError):
        return "", "", 0
```

In `RealDuffelClient.search_flights`, replace the list comprehension building `options` with a loop that computes the times once per offer:

```python
        options = []
        for offer in offers[:_MAX_OFFERS]:
            depart_at, arrive_at, stops = _leg_times(offer)
            options.append(
                FlightOption(
                    id=offer["id"],
                    airline=offer["owner"]["name"],
                    fare_class=_cabin_class(offer),
                    origin=origin,
                    destination=destination,
                    depart_date=depart_date,
                    price_cents=_to_cents(offer["total_amount"]),
                    passenger_ids=passenger_ids,
                    currency=offer["total_currency"],
                    depart_at=depart_at,
                    arrive_at=arrive_at,
                    stops=stops,
                )
            )
```

- [ ] **Step 4: Give the mock client times**

In `api/travel/duffel_client.py`, above `class MockDuffelClient`, add:

```python
# Fixture schedule: an early, a midday and an evening departure, so a presence
# window ("be in Chicago by 2pm") actually discriminates between them instead
# of accepting or rejecting all three together.
_MOCK_DEPART_HOURS = [7, 12, 19]
_MOCK_DURATIONS_H = [4, 5, 4]
_MOCK_STOPS = [0, 1, 0]
# ponytail: one zone for every mock airport. Real zones need an airport->tz
# table the mock has no reason to carry; RealDuffelClient gets them from Duffel.
_MOCK_ZONE = ZoneInfo("America/Los_Angeles")
```

Replace `MockDuffelClient.search_flights` with:

```python
    def search_flights(
        self, origin: str, destination: str, depart_date: str
    ) -> list[FlightOption]:
        day = datetime.fromisoformat(depart_date).date()
        options = []
        for i in range(3):
            depart = datetime.combine(
                day, time(_MOCK_DEPART_HOURS[i]), tzinfo=_MOCK_ZONE
            )
            arrive = depart + timedelta(hours=_MOCK_DURATIONS_H[i])
            options.append(
                FlightOption(
                    id=str(uuid.uuid4()),
                    airline=_AIRLINES[i % len(_AIRLINES)],
                    fare_class=_FARE_CLASSES[i % len(_FARE_CLASSES)],
                    origin=origin,
                    destination=destination,
                    depart_date=depart_date,
                    price_cents=28000 + i * 15000,
                    depart_at=depart.isoformat(),
                    arrive_at=arrive.isoformat(),
                    stops=_MOCK_STOPS[i],
                )
            )
        return options
```

- [ ] **Step 5: Run the full suite and lint**

Run: `cd api && .venv/Scripts/python.exe -m pytest && .venv/Scripts/python.exe -m ruff check .`
Expected: all pass, no lint findings.

- [ ] **Step 6: Commit**

```bash
git add api/travel/duffel_client.py api/tests/
git commit -m "feat(travel): populate flight instants from Duffel segments and the mock"
```

---

### Task 4: Planning domain models

**Files:**
- Create: `api/planning/__init__.py` (empty), `api/planning/models.py`
- Test: `api/tests/test_planning_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces (all in `api/planning/models.py`, consumed by Tasks 5–9):
  `Meeting`, `TripIntent`, `Leg`, `Itinerary`, `Violation`, `PlanResult`,
  `RiskFactor`, `RiskAssessment`, `Ranking`, and
  `Itinerary.total_price_cents` derived in `Itinerary.from_legs`.

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_planning_models.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest

from planning.models import Itinerary, Leg, Meeting, TripIntent

UTC = timezone.utc


def _leg(price=10000, **kw):
    base = {
        "origin": "SFO", "destination": "ORD",
        "depart_at": datetime(2026, 9, 1, 7, tzinfo=UTC),
        "arrive_at": datetime(2026, 9, 1, 13, tzinfo=UTC),
        "airline": "United", "fare_class": "economy", "price_cents": price,
    }
    return Leg(**{**base, **kw})


def test_itinerary_totals_its_legs():
    itinerary = Itinerary.from_legs([_leg(10000), _leg(15000)])
    assert itinerary.total_price_cents == 25000


def test_meeting_rejects_a_naive_datetime():
    """Every comparison in the solver is instant-to-instant. A naive datetime
    would raise deep inside the solver instead of at the boundary."""
    with pytest.raises(ValueError, match="timezone-aware"):
        Meeting(
            title="Pitch", city="ORD", mode="in_person",
            starts_at=datetime(2026, 9, 1, 14),           # no tzinfo
            ends_at=datetime(2026, 9, 1, 15, tzinfo=UTC),
        )


def test_meeting_rejects_a_backwards_interval():
    with pytest.raises(ValueError, match="ends_at"):
        Meeting(
            title="Pitch", city="ORD", mode="in_person",
            starts_at=datetime(2026, 9, 1, 15, tzinfo=UTC),
            ends_at=datetime(2026, 9, 1, 14, tzinfo=UTC),
        )


def test_in_person_meeting_requires_a_city():
    """Mirrors the DB check constraint. A guessed city books a real ticket to
    the wrong place, so this fails rather than defaulting."""
    with pytest.raises(ValueError, match="city"):
        Meeting(
            title="Pitch", mode="in_person",
            starts_at=datetime(2026, 9, 1, 14, tzinfo=UTC),
            ends_at=datetime(2026, 9, 1, 15, tzinfo=UTC),
        )


def test_virtual_meeting_needs_no_city():
    meeting = Meeting(
        title="Board call", mode="virtual",
        starts_at=datetime(2026, 9, 2, 17, tzinfo=UTC),
        ends_at=datetime(2026, 9, 2, 18, tzinfo=UTC),
    )
    assert meeting.city is None
    assert meeting.flexible is False  # binding unless said otherwise


def test_trip_intent_defaults_are_permissive_but_present():
    intent = TripIntent(origin_city="SFO", meetings=[])
    assert intent.budget_cents is None
    assert intent.preferences == {}
    assert intent.policy_rules == {}
    assert intent.binding_meetings() == []


def test_binding_meetings_excludes_flexible_ones():
    hard = Meeting(
        title="Pitch", city="ORD", mode="in_person",
        starts_at=datetime(2026, 9, 1, 14, tzinfo=UTC),
        ends_at=datetime(2026, 9, 1, 15, tzinfo=UTC),
    )
    soft = hard.model_copy(update={"title": "Optional sync", "flexible": True})
    intent = TripIntent(origin_city="SFO", meetings=[hard, soft])
    assert [m.title for m in intent.binding_meetings()] == ["Pitch"]


def test_leg_duration_and_same_day_helpers():
    leg = _leg()
    assert leg.duration == timedelta(hours=6)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd api && .venv/Scripts/python.exe -m pytest tests/test_planning_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'planning'`.

- [ ] **Step 3: Write the models**

Create `api/planning/__init__.py` (empty file).

Create `api/planning/models.py`:

```python
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
    kind: str                    # presence | no_fly | budget | policy | red_eye | connections | no_flights
    severity: Literal["hard", "soft"]
    message: str
    meeting_id: str | None = None


class TripIntent(BaseModel):
    origin_city: str
    meetings: list[Meeting] = Field(default_factory=list)
    budget_cents: int | None = None
    preferences: dict = Field(default_factory=dict)
    policy_rules: dict = Field(default_factory=dict)

    def binding_meetings(self) -> list["Meeting"]:
        return [m for m in self.meetings if not m.flexible]

    def in_person(self) -> list["Meeting"]:
        return [m for m in self.binding_meetings() if m.mode == "in_person"]

    def virtual(self) -> list["Meeting"]:
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
    # Duffel offers on aggregator content go stale within seconds, so this is
    # a hint for repricing, never something to book from directly.
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
```

- [ ] **Step 4: Run the tests**

Run: `cd api && .venv/Scripts/python.exe -m pytest tests/test_planning_models.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add api/planning/ api/tests/test_planning_models.py
git commit -m "feat(planning): domain models for meetings, intent, legs and itineraries"
```

---

### Task 5: Constraint checkers

**Files:**
- Create: `api/planning/checkers.py`
- Test: `api/tests/test_planning_checkers.py`

**Interfaces:**
- Consumes: `Meeting`, `TripIntent`, `Itinerary`, `Leg`, `Violation` (Task 4); `check_rules` from `api/policy/rules.py`.
- Produces:
  - `GROUND_BUFFER: timedelta`, `AIRPORT_LEAD: timedelta`
  - `Checker = Callable[[Itinerary, TripIntent], list[Violation]]`
  - `HARD_CHECKERS: list[Checker]`, `SOFT_CHECKERS: list[Checker]`
  - `check_presence`, `check_no_fly`, `check_red_eye`, `check_connections`, `check_budget`, `check_policy`
  - `occupancy(itinerary, origin_city) -> list[tuple[str | None, datetime, datetime]]`
  Task 6 imports `HARD_CHECKERS`, `SOFT_CHECKERS`, `GROUND_BUFFER`, `AIRPORT_LEAD`.

- [ ] **Step 1: Write the failing tests**

Create `api/tests/test_planning_checkers.py`:

```python
from datetime import datetime, timezone

from planning.checkers import (
    check_budget,
    check_connections,
    check_no_fly,
    check_policy,
    check_presence,
    check_red_eye,
)
from planning.models import Itinerary, Leg, Meeting, TripIntent

UTC = timezone.utc


def at(day, hour, minute=0):
    return datetime(2026, 9, day, hour, minute, tzinfo=UTC)


def leg(origin, dest, depart, arrive, price=30000, stops=0, fare="economy"):
    return Leg(
        origin=origin, destination=dest, depart_at=depart, arrive_at=arrive,
        airline="United", fare_class=fare, price_cents=price, stops=stops,
    )


def meeting(city, start, end, mode="in_person", flexible=False, mid="m1"):
    return Meeting(
        id=mid, title="Meeting", city=city, mode=mode,
        starts_at=start, ends_at=end, flexible=flexible,
    )


def intent(meetings, **kw):
    return TripIntent(origin_city="SFO", meetings=meetings, **kw)


# --- presence -------------------------------------------------------------

def test_presence_accepts_a_comfortable_arrival():
    itinerary = Itinerary.from_legs([leg("SFO", "ORD", at(1, 6), at(1, 11))])
    trip = intent([meeting("ORD", at(1, 14), at(1, 15))])
    assert check_presence(itinerary, trip) == []


def test_presence_rejects_landing_twenty_minutes_before_the_meeting():
    """Landing is not being there -- deplaning, bags and a cab are real, and
    GROUND_BUFFER is what encodes that."""
    itinerary = Itinerary.from_legs([leg("SFO", "ORD", at(1, 9), at(1, 13, 40))])
    trip = intent([meeting("ORD", at(1, 14), at(1, 15))])
    violations = check_presence(itinerary, trip)
    assert [v.kind for v in violations] == ["presence"]
    assert violations[0].meeting_id == "m1"


def test_presence_rejects_leaving_before_the_meeting_ends():
    itinerary = Itinerary.from_legs([
        leg("SFO", "ORD", at(1, 6), at(1, 11)),
        leg("ORD", "SFO", at(1, 14, 30), at(1, 18)),
    ])
    trip = intent([meeting("ORD", at(1, 14), at(1, 16))])
    assert [v.kind for v in check_presence(itinerary, trip)] == ["presence"]


def test_presence_rejects_being_in_the_wrong_city_entirely():
    itinerary = Itinerary.from_legs([leg("SFO", "DEN", at(1, 6), at(1, 10))])
    trip = intent([meeting("ORD", at(1, 14), at(1, 15))])
    assert [v.kind for v in check_presence(itinerary, trip)] == ["presence"]


def test_presence_ignores_a_flexible_meeting():
    itinerary = Itinerary.from_legs([leg("SFO", "DEN", at(1, 6), at(1, 10))])
    trip = intent([meeting("ORD", at(1, 14), at(1, 15), flexible=True)])
    assert check_presence(itinerary, trip) == []


def test_presence_handles_meetings_across_timezones():
    """2pm Chicago is 12pm Denver. A solver comparing wall clocks would call
    this feasible; comparing instants shows the traveler is still airborne."""
    chicago_2pm = datetime(2026, 9, 1, 19, tzinfo=UTC)     # 14:00 CDT
    itinerary = Itinerary.from_legs([
        leg("SFO", "ORD", datetime(2026, 9, 1, 16, tzinfo=UTC),
            datetime(2026, 9, 1, 20, tzinfo=UTC))          # lands 15:00 CDT
    ])
    trip = intent([meeting("ORD", chicago_2pm,
                           datetime(2026, 9, 1, 20, 30, tzinfo=UTC))])
    assert [v.kind for v in check_presence(itinerary, trip)] == ["presence"]


# --- no-fly ---------------------------------------------------------------

def test_no_fly_rejects_a_binding_virtual_meeting_taken_in_the_air():
    itinerary = Itinerary.from_legs([leg("SFO", "ORD", at(1, 9), at(1, 14))])
    trip = intent([meeting(None, at(1, 10), at(1, 11), mode="virtual", mid="v1")])
    violations = check_no_fly(itinerary, trip)
    assert [v.kind for v in violations] == ["no_fly"]
    assert violations[0].meeting_id == "v1"


def test_no_fly_allows_a_call_on_the_ground_between_flights():
    """The buffered transit window blocks presence, not connectivity -- you
    can take a call in a lounge. Only genuinely airborne time counts."""
    itinerary = Itinerary.from_legs([leg("SFO", "ORD", at(1, 9), at(1, 14))])
    trip = intent([meeting(None, at(1, 15), at(1, 16), mode="virtual")])
    assert check_no_fly(itinerary, trip) == []


def test_no_fly_relaxes_for_a_flexible_virtual_meeting():
    itinerary = Itinerary.from_legs([leg("SFO", "ORD", at(1, 9), at(1, 14))])
    trip = intent([
        meeting(None, at(1, 10), at(1, 11), mode="virtual", flexible=True)
    ])
    assert check_no_fly(itinerary, trip) == []


# --- soft checkers --------------------------------------------------------

def test_red_eye_flags_a_late_night_departure_when_the_traveler_avoids_them():
    itinerary = Itinerary.from_legs([leg("SFO", "ORD", at(1, 23), at(2, 5))])
    trip = intent([], preferences={"avoid_red_eyes": True})
    assert [v.kind for v in check_red_eye(itinerary, trip)] == ["red_eye"]


def test_red_eye_is_silent_when_the_traveler_does_not_care():
    itinerary = Itinerary.from_legs([leg("SFO", "ORD", at(1, 23), at(2, 5))])
    assert check_red_eye(itinerary, intent([])) == []


def test_connections_flags_more_stops_than_the_traveler_accepts():
    itinerary = Itinerary.from_legs([leg("SFO", "ORD", at(1, 6), at(1, 16), stops=2)])
    trip = intent([], preferences={"max_connections": 1})
    assert [v.kind for v in check_connections(itinerary, trip)] == ["connections"]


def test_budget_flags_going_over_and_stays_quiet_under():
    itinerary = Itinerary.from_legs([leg("SFO", "ORD", at(1, 6), at(1, 11), price=90000)])
    assert [v.kind for v in check_budget(itinerary, intent([], budget_cents=50000))] == ["budget"]
    assert check_budget(itinerary, intent([], budget_cents=100000)) == []
    assert check_budget(itinerary, intent([])) == []      # no budget set


def test_policy_is_soft_so_an_out_of_policy_plan_is_shown_and_flagged():
    """Hiding it would make the planner less useful than the chat it replaces
    -- the manager approval path already exists for exactly this."""
    itinerary = Itinerary.from_legs([
        leg("SFO", "ORD", at(1, 6), at(1, 11), fare="business")
    ])
    trip = intent([], policy_rules={
        "max_fare_class": "economy",
        "max_hotel_nightly_rate_cents": 25000,
        "approval_threshold_cents": 150000,
    })
    violations = check_policy(itinerary, trip)
    assert [v.severity for v in violations] == ["soft"]
    assert "business" in violations[0].message


def test_policy_is_silent_with_no_rules_configured():
    itinerary = Itinerary.from_legs([leg("SFO", "ORD", at(1, 6), at(1, 11))])
    assert check_policy(itinerary, intent([])) == []
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd api && .venv/Scripts/python.exe -m pytest tests/test_planning_checkers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'planning.checkers'`.

- [ ] **Step 3: Write the checkers**

Create `api/planning/checkers.py`:

```python
"""Constraint checkers — the code half of the planner.

Every checker has the same signature, `(itinerary, intent) -> list[Violation]`,
and the two lists at the bottom are the whole extension point. International
support adds `check_visa` and `check_passport_validity` to HARD_CHECKERS and
changes nothing else: the solver, the infeasibility search and the UI all read
these lists rather than knowing what's in them.

Hard means infeasible — the itinerary is not shown. Soft means shown and
flagged. Policy is deliberately soft: an out-of-policy plan routes to the
manager approval path that already exists, and hiding it would make the
planner strictly worse than the chat it replaces.
"""
from collections.abc import Callable
from datetime import datetime, timedelta

from planning.models import Itinerary, TripIntent, Violation
from policy.rules import check_rules
from travel.models import FlightOption

# Airport <-> meeting: deplaning, bags, ground transport, and enough slack that
# a 20-minute taxi delay doesn't cost the meeting. Domestic figures.
GROUND_BUFFER = timedelta(minutes=90)
# At the airport before departure. Combined with GROUND_BUFFER this is the
# ~3.5h a traveler really needs between a meeting ending and a wheels-up.
AIRPORT_LEAD = timedelta(minutes=120)

# Red-eye window, local time at the departure airport.
_RED_EYE_FROM, _RED_EYE_TO = 22, 5

Checker = Callable[[Itinerary, TripIntent], list[Violation]]


def occupancy(
    itinerary: Itinerary, origin_city: str
) -> list[tuple[str | None, datetime, datetime]]:
    """Where the traveler effectively is, over time.

    `None` marks a transit window — buffered wider than the flight itself,
    because a traveler an hour from landing is not available for an in-person
    meeting. Segments are returned in order and cover the whole timeline;
    the first and last are open-ended (represented by datetime.min/max in the
    first leg's timezone).
    """
    if not itinerary.legs:
        return []

    tz = itinerary.legs[0].depart_at.tzinfo
    segments: list[tuple[str | None, datetime, datetime]] = []
    here = origin_city
    cursor = datetime.min.replace(tzinfo=tz)

    for leg in itinerary.legs:
        transit_from = leg.depart_at - AIRPORT_LEAD - GROUND_BUFFER
        transit_to = leg.arrive_at + GROUND_BUFFER
        segments.append((here, cursor, transit_from))
        segments.append((None, transit_from, transit_to))
        here, cursor = leg.destination, transit_to

    segments.append((here, cursor, datetime.max.replace(tzinfo=tz)))
    return segments


def check_presence(itinerary: Itinerary, intent: TripIntent) -> list[Violation]:
    """A binding in-person meeting must fall entirely inside one stay in its
    own city — not straddle a departure, not start while still in transit."""
    segments = occupancy(itinerary, intent.origin_city)
    violations = []
    for meeting in intent.in_person():
        present = any(
            city == meeting.city and start <= meeting.starts_at
            and meeting.ends_at <= end
            for city, start, end in segments
        )
        if not present:
            violations.append(
                Violation(
                    kind="presence",
                    severity="hard",
                    meeting_id=meeting.id or None,
                    message=(
                        f"Not on the ground in {meeting.city} for "
                        f"{meeting.title!r} ({meeting.starts_at.isoformat()})."
                    ),
                )
            )
    return violations


def check_no_fly(itinerary: Itinerary, intent: TripIntent) -> list[Violation]:
    """A binding virtual meeting may not overlap airborne time.

    Airborne, not the buffered transit window: a call can be taken from a
    lounge, so only wheels-up to wheels-down counts.
    """
    violations = []
    for meeting in intent.virtual():
        for leg in itinerary.legs:
            if meeting.starts_at < leg.arrive_at and leg.depart_at < meeting.ends_at:
                violations.append(
                    Violation(
                        kind="no_fly",
                        severity="hard",
                        meeting_id=meeting.id or None,
                        message=(
                            f"{meeting.title!r} runs while airborne on "
                            f"{leg.origin}→{leg.destination}."
                        ),
                    )
                )
                break
    return violations


def check_red_eye(itinerary: Itinerary, intent: TripIntent) -> list[Violation]:
    if not intent.preferences.get("avoid_red_eyes"):
        return []
    return [
        Violation(
            kind="red_eye",
            severity="soft",
            message=(
                f"{leg.origin}→{leg.destination} departs "
                f"{leg.depart_at.strftime('%H:%M')} local."
            ),
        )
        for leg in itinerary.legs
        if leg.depart_at.hour >= _RED_EYE_FROM or leg.depart_at.hour < _RED_EYE_TO
    ]


def check_connections(itinerary: Itinerary, intent: TripIntent) -> list[Violation]:
    cap = intent.preferences.get("max_connections")
    if cap is None:
        return []
    return [
        Violation(
            kind="connections",
            severity="soft",
            message=(
                f"{leg.origin}→{leg.destination} has {leg.stops} stop(s), "
                f"more than the {cap} you prefer."
            ),
        )
        for leg in itinerary.legs
        if leg.stops > cap
    ]


def check_budget(itinerary: Itinerary, intent: TripIntent) -> list[Violation]:
    if intent.budget_cents is None or itinerary.total_price_cents <= intent.budget_cents:
        return []
    over = itinerary.total_price_cents - intent.budget_cents
    return [
        Violation(
            kind="budget",
            severity="soft",
            message=f"${over / 100:,.0f} over the trip budget.",
        )
    ]


def check_policy(itinerary: Itinerary, intent: TripIntent) -> list[Violation]:
    """Reuses the existing deterministic rule check, one leg at a time, so
    the planner and the chat agent can never disagree about what's in policy."""
    if not intent.policy_rules:
        return []
    violations = []
    for leg in itinerary.legs:
        option = FlightOption(
            id=leg.offer_id or "",
            airline=leg.airline,
            fare_class=leg.fare_class,
            origin=leg.origin,
            destination=leg.destination,
            depart_date=leg.depart_at.date().isoformat(),
            price_cents=leg.price_cents,
        )
        result = check_rules(option, intent.policy_rules)
        violations.extend(
            Violation(kind="policy", severity="soft", message=message)
            for message in result.violations
        )
    return violations


HARD_CHECKERS: list[Checker] = [check_presence, check_no_fly]
SOFT_CHECKERS: list[Checker] = [check_red_eye, check_connections, check_budget, check_policy]
```

- [ ] **Step 4: Run the tests and lint**

Run: `cd api && .venv/Scripts/python.exe -m pytest tests/test_planning_checkers.py -v && .venv/Scripts/python.exe -m ruff check .`
Expected: PASS (16 tests), no lint findings.

- [ ] **Step 5: Commit**

```bash
git add api/planning/checkers.py api/tests/test_planning_checkers.py
git commit -m "feat(planning): pluggable hard/soft constraint checkers"
```

---

### Task 6: The solver

**Files:**
- Create: `api/planning/solver.py`
- Test: `api/tests/test_planning_solver.py`

**Interfaces:**
- Consumes: Task 4 models, Task 5 checkers, `FlightOption` (Task 2).
- Produces:
  - `SearchFn = Callable[[str, str, str], list[FlightOption]]` — `(origin, destination, "YYYY-MM-DD")`
  - `solve(intent: TripIntent, search: SearchFn) -> PlanResult`
  - `city_sequence(intent: TripIntent) -> list[str]`
  - `MAX_ITINERARIES: int`
  Task 8 (routes) calls `solve`.

- [ ] **Step 1: Write the failing tests**

Create `api/tests/test_planning_solver.py`:

```python
from datetime import datetime, timedelta, timezone

from planning.models import Meeting, TripIntent
from planning.solver import city_sequence, solve
from travel.models import FlightOption

UTC = timezone.utc


def at(day, hour, minute=0):
    return datetime(2026, 9, day, hour, minute, tzinfo=UTC)


def flight(origin, dest, depart, hours=4, price=30000, airline="United", stops=0):
    arrive = depart + timedelta(hours=hours)
    return FlightOption(
        id=f"{origin}{dest}-{depart.isoformat()}",
        airline=airline, fare_class="economy", origin=origin, destination=dest,
        depart_date=depart.date().isoformat(), price_cents=price,
        depart_at=depart.isoformat(), arrive_at=arrive.isoformat(), stops=stops,
    )


def fixture_search(catalog):
    """Build a SearchFn over a fixed catalog. This is why `solve` takes search
    as a parameter — the whole solver is testable with no network and no
    monkeypatching."""
    def search(origin, destination, date):
        return [
            f for f in catalog
            if f.origin == origin and f.destination == destination
            and f.depart_date == date
        ]
    return search


def meeting(city, start, end, mode="in_person", flexible=False, mid="m1", title="Meeting"):
    return Meeting(id=mid, title=title, city=city, mode=mode,
                   starts_at=start, ends_at=end, flexible=flexible)


# --- city sequence --------------------------------------------------------

def test_city_sequence_is_origin_then_meeting_cities_then_home():
    intent = TripIntent(origin_city="SFO", meetings=[
        meeting("ORD", at(1, 14), at(1, 15), mid="a"),
        meeting("DEN", at(3, 10), at(3, 11), mid="b"),
    ])
    assert city_sequence(intent) == ["SFO", "ORD", "DEN", "SFO"]


def test_city_sequence_collapses_consecutive_meetings_in_one_city():
    intent = TripIntent(origin_city="SFO", meetings=[
        meeting("ORD", at(1, 14), at(1, 15), mid="a"),
        meeting("ORD", at(2, 9), at(2, 10), mid="b"),
    ])
    assert city_sequence(intent) == ["SFO", "ORD", "SFO"]


def test_city_sequence_ignores_virtual_meetings():
    intent = TripIntent(origin_city="SFO", meetings=[
        meeting("ORD", at(1, 14), at(1, 15), mid="a"),
        meeting(None, at(2, 9), at(2, 10), mode="virtual", mid="b"),
    ])
    assert city_sequence(intent) == ["SFO", "ORD", "SFO"]


# --- feasibility ----------------------------------------------------------

def test_solve_returns_only_itineraries_that_make_the_meeting():
    catalog = [
        flight("SFO", "ORD", at(1, 6)),            # lands 10:00 -- works
        flight("SFO", "ORD", at(1, 13)),           # lands 17:00 -- too late
        flight("ORD", "SFO", at(1, 19)),           # home after the meeting
    ]
    intent = TripIntent(origin_city="SFO", meetings=[
        meeting("ORD", at(1, 14), at(1, 15))
    ])

    result = solve(intent, fixture_search(catalog))

    assert result.binding_constraint is None
    assert len(result.itineraries) == 1
    outbound = result.itineraries[0].legs[0]
    assert outbound.depart_at == at(1, 6)


def test_solve_chains_two_cities_in_order():
    catalog = [
        flight("SFO", "ORD", at(1, 6)),
        flight("ORD", "DEN", at(2, 6), hours=3),
        flight("DEN", "SFO", at(2, 20), hours=3),
    ]
    intent = TripIntent(origin_city="SFO", meetings=[
        meeting("ORD", at(1, 14), at(1, 15), mid="a"),
        meeting("DEN", at(2, 14), at(2, 15), mid="b"),
    ])

    result = solve(intent, fixture_search(catalog))

    assert len(result.itineraries) == 1
    assert [(leg.origin, leg.destination) for leg in result.itineraries[0].legs] == [
        ("SFO", "ORD"), ("ORD", "DEN"), ("DEN", "SFO")
    ]


def test_solve_finds_the_night_before_flight_for_an_early_meeting():
    """A 9am meeting is reached by flying the day before, so the solver has to
    search the deadline date *and* the day before it."""
    catalog = [
        flight("SFO", "ORD", at(1, 18)),           # lands 22:00 the night before
        flight("ORD", "SFO", at(2, 16)),
    ]
    intent = TripIntent(origin_city="SFO", meetings=[
        meeting("ORD", at(2, 9), at(2, 10))
    ])

    result = solve(intent, fixture_search(catalog))

    assert len(result.itineraries) == 1
    assert result.itineraries[0].legs[0].depart_at == at(1, 18)


def test_solve_sorts_by_total_price_and_caps_the_set():
    catalog = [
        flight("SFO", "ORD", at(1, 6), price=50000, airline="A"),
        flight("SFO", "ORD", at(1, 7), price=20000, airline="B"),
        flight("ORD", "SFO", at(1, 19), price=10000),
    ]
    intent = TripIntent(origin_city="SFO", meetings=[
        meeting("ORD", at(1, 14), at(1, 15))
    ])

    result = solve(intent, fixture_search(catalog))

    totals = [i.total_price_cents for i in result.itineraries]
    assert totals == sorted(totals)
    assert totals[0] == 30000


def test_solve_attaches_soft_violations_without_hiding_the_itinerary():
    catalog = [
        flight("SFO", "ORD", at(1, 6), price=200000),
        flight("ORD", "SFO", at(1, 19), price=10000),
    ]
    intent = TripIntent(
        origin_city="SFO",
        meetings=[meeting("ORD", at(1, 14), at(1, 15))],
        budget_cents=100000,
    )

    result = solve(intent, fixture_search(catalog))

    assert len(result.itineraries) == 1
    assert [v.kind for v in result.itineraries[0].soft_violations] == ["budget"]


def test_solve_respects_a_binding_virtual_meeting():
    catalog = [
        flight("SFO", "ORD", at(1, 6)),            # airborne 06:00-10:00
        flight("SFO", "ORD", at(1, 10, 30)),       # airborne 10:30-14:30 -- too late anyway
        flight("ORD", "SFO", at(1, 22)),
    ]
    intent = TripIntent(origin_city="SFO", meetings=[
        meeting("ORD", at(1, 18), at(1, 19), mid="a"),
        meeting(None, at(1, 7), at(1, 8), mode="virtual", mid="v", title="Board call"),
    ])

    result = solve(intent, fixture_search(catalog))

    assert result.itineraries == []
    assert result.binding_constraint.kind == "no_fly"
    assert "Board call" in result.binding_constraint.message


def test_a_flexible_virtual_meeting_unblocks_the_same_search():
    catalog = [
        flight("SFO", "ORD", at(1, 6)),
        flight("ORD", "SFO", at(1, 22)),
    ]
    intent = TripIntent(origin_city="SFO", meetings=[
        meeting("ORD", at(1, 18), at(1, 19), mid="a"),
        meeting(None, at(1, 7), at(1, 8), mode="virtual", mid="v", flexible=True),
    ])

    result = solve(intent, fixture_search(catalog))

    assert len(result.itineraries) == 1
    assert result.binding_constraint is None


def test_solve_names_presence_as_the_binding_constraint_when_timing_is_impossible():
    catalog = [
        flight("SFO", "ORD", at(1, 13)),           # lands 17:00, meeting is at 14:00
        flight("ORD", "SFO", at(1, 22)),
    ]
    intent = TripIntent(origin_city="SFO", meetings=[
        meeting("ORD", at(1, 14), at(1, 15), title="Client pitch")
    ])

    result = solve(intent, fixture_search(catalog))

    assert result.itineraries == []
    assert result.binding_constraint.kind == "presence"
    assert result.relaxation


def test_solve_reports_no_flights_when_the_route_does_not_exist():
    intent = TripIntent(origin_city="SFO", meetings=[
        meeting("ORD", at(1, 14), at(1, 15))
    ])

    result = solve(intent, fixture_search([]))

    assert result.itineraries == []
    assert result.binding_constraint.kind == "no_flights"


def test_solve_with_no_in_person_meetings_plans_no_travel():
    """A trip of only virtual meetings needs no flights, and that is a
    feasible answer -- not an error and not an empty list."""
    intent = TripIntent(origin_city="SFO", meetings=[
        meeting(None, at(1, 9), at(1, 10), mode="virtual")
    ])

    result = solve(intent, fixture_search([]))

    assert result.binding_constraint is None
    assert result.itineraries == [] or result.itineraries[0].legs == []


def test_solve_skips_flights_with_no_usable_times():
    """An offer with blank instants is still bookable through chat, but it
    cannot take part in constraint solving -- silently including it would
    produce a plan the solver never actually verified."""
    untimed = FlightOption(
        id="untimed", airline="United", fare_class="economy", origin="SFO",
        destination="ORD", depart_date="2026-09-01", price_cents=10000,
    )
    catalog = [untimed, flight("SFO", "ORD", at(1, 6)), flight("ORD", "SFO", at(1, 19))]
    intent = TripIntent(origin_city="SFO", meetings=[
        meeting("ORD", at(1, 14), at(1, 15))
    ])

    result = solve(intent, fixture_search(catalog))

    assert all(leg.offer_id != "untimed"
               for i in result.itineraries for leg in i.legs)


def test_solve_handles_a_dst_boundary():
    """US DST ends 2026-11-01. A trip spanning it must still land before the
    meeting -- naive arithmetic on local times drifts by an hour here."""
    from zoneinfo import ZoneInfo

    chicago = ZoneInfo("America/Chicago")
    depart = datetime(2026, 10, 31, 18, tzinfo=ZoneInfo("America/Los_Angeles"))
    option = FlightOption(
        id="dst", airline="United", fare_class="economy", origin="SFO",
        destination="ORD", depart_date="2026-10-31", price_cents=30000,
        depart_at=depart.isoformat(),
        arrive_at=(depart + timedelta(hours=4)).isoformat(),
    )
    home = FlightOption(
        id="dst-home", airline="United", fare_class="economy", origin="ORD",
        destination="SFO", depart_date="2026-11-01", price_cents=30000,
        depart_at=datetime(2026, 11, 1, 18, tzinfo=chicago).isoformat(),
        arrive_at=datetime(2026, 11, 1, 21, tzinfo=chicago).isoformat(),
    )
    intent = TripIntent(origin_city="SFO", meetings=[
        meeting("ORD", datetime(2026, 11, 1, 9, tzinfo=chicago),
                datetime(2026, 11, 1, 10, tzinfo=chicago))
    ])

    result = solve(intent, fixture_search([option, home]))

    assert len(result.itineraries) == 1
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd api && .venv/Scripts/python.exe -m pytest tests/test_planning_solver.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'planning.solver'`.

- [ ] **Step 3: Write the solver**

Create `api/planning/solver.py`:

```python
"""The solver — the code half of the planner, and a pure function.

`search` is injected rather than imported so the whole thing is table-testable
against fixtures with no network and no monkeypatching of module globals. That
isolation is the point: this is where correctness lives.

It enumerates itineraries that satisfy every hard constraint, ranks them by
price, and attaches soft violations. When nothing is feasible it does not
return an empty list — an empty list is the one answer a traveler can do
nothing with. It returns the constraint that is actually blocking.
"""
from collections.abc import Callable
from datetime import date, datetime, timedelta
from itertools import product

from planning.checkers import (
    AIRPORT_LEAD,
    GROUND_BUFFER,
    HARD_CHECKERS,
    SOFT_CHECKERS,
    Checker,
    check_no_fly,
)
from planning.models import Itinerary, Leg, Meeting, PlanResult, TripIntent, Violation
from travel.models import FlightOption

SearchFn = Callable[[str, str, str], list[FlightOption]]

# The judge reasons over a handful, not a combinatorial explosion, and every
# extra option is tokens spent to make a worse-ranked plan legible.
MAX_ITINERARIES = 5


def city_sequence(intent: TripIntent) -> list[str]:
    """origin -> binding in-person cities in time order -> origin.

    Consecutive duplicates collapse: two meetings in Chicago on consecutive
    days is one stay, not a flight out and back.
    """
    cities = [intent.origin_city]
    for meeting in sorted(intent.in_person(), key=lambda m: m.starts_at):
        if meeting.city != cities[-1]:
            cities.append(meeting.city)
    if len(cities) == 1:
        return cities
    return [*cities, intent.origin_city]


def _stays(intent: TripIntent) -> dict[str, tuple[datetime, datetime]]:
    """city -> (be on the ground by, may leave after).

    ponytail: keyed by city, so a trip that visits one city twice merges both
    visits into a single window. Fine for the 2-3 meeting trips this slice
    targets; key by (city, leg index) when a real revisit shows up.
    """
    windows: dict[str, tuple[datetime, datetime]] = {}
    for meeting in intent.in_person():
        be_there_by = meeting.starts_at - GROUND_BUFFER
        may_leave = meeting.ends_at + GROUND_BUFFER + AIRPORT_LEAD
        if meeting.city in windows:
            existing = windows[meeting.city]
            windows[meeting.city] = (min(existing[0], be_there_by), max(existing[1], may_leave))
        else:
            windows[meeting.city] = (be_there_by, may_leave)
    return windows


def _to_leg(option: FlightOption) -> Leg | None:
    """A flight with no readable schedule cannot be constraint-solved.
    Dropping it beats including a leg whose timing was never verified."""
    if not option.depart_at or not option.arrive_at:
        return None
    try:
        depart = datetime.fromisoformat(option.depart_at)
        arrive = datetime.fromisoformat(option.arrive_at)
    except ValueError:
        return None
    if depart.tzinfo is None or arrive.tzinfo is None or arrive <= depart:
        return None
    return Leg(
        origin=option.origin,
        destination=option.destination,
        depart_at=depart,
        arrive_at=arrive,
        airline=option.airline,
        fare_class=option.fare_class,
        price_cents=option.price_cents,
        stops=option.stops,
        offer_id=option.id,
    )


def _candidate_dates(anchor: datetime, before: bool) -> list[str]:
    """The deadline's own date, plus the day before it — an early meeting is
    usually reached by flying the night before. For the return hop the extra
    day goes forwards instead."""
    day: date = anchor.date()
    other = day - timedelta(days=1) if before else day + timedelta(days=1)
    return [d.isoformat() for d in sorted({day, other})]


def _hop_candidates(
    origin: str, destination: str, search: SearchFn, anchor: datetime, before: bool
) -> list[Leg]:
    legs: list[Leg] = []
    for day in _candidate_dates(anchor, before):
        for option in search(origin, destination, day):
            leg = _to_leg(option)
            if leg is not None:
                legs.append(leg)
    return legs


def _combinations(hops: list[list[Leg]], stays: dict[str, tuple[datetime, datetime]]):
    """Cartesian product across hops, pruned as it goes.

    A combination survives only if each leg departs after the traveler is
    allowed to leave the city they're in, and lands before they're due in the
    next one. Pruning here rather than after the product is what keeps this
    from blowing up on three hops with five options each.
    """
    for combination in product(*hops):
        ok = True
        previous: Leg | None = None
        for leg in combination:
            if previous is not None and leg.depart_at < previous.arrive_at:
                ok = False
                break
            window = stays.get(leg.destination)
            if window is not None and leg.arrive_at > window[0]:
                ok = False
                break
            departing_from = stays.get(leg.origin)
            if departing_from is not None and leg.depart_at < departing_from[1]:
                ok = False
                break
            previous = leg
        if ok:
            yield list(combination)


def _feasible(
    intent: TripIntent, search: SearchFn, hard: list[Checker]
) -> list[Itinerary]:
    cities = city_sequence(intent)
    if len(cities) == 1:
        return [Itinerary.from_legs([])]     # virtual-only trip: no travel needed

    stays = _stays(intent)
    hops: list[list[Leg]] = []
    for i in range(len(cities) - 1):
        origin, destination = cities[i], cities[i + 1]
        returning = i == len(cities) - 2
        anchor = stays[origin][1] if returning else stays[destination][0]
        candidates = _hop_candidates(origin, destination, search, anchor, not returning)
        if not candidates:
            return []
        hops.append(candidates)

    itineraries = []
    for legs in _combinations(hops, stays):
        itinerary = Itinerary.from_legs(legs)
        if any(checker(itinerary, intent) for checker in hard):
            continue
        itineraries.append(itinerary)

    itineraries.sort(key=lambda i: i.total_price_cents)
    return itineraries[:MAX_ITINERARIES]


def _binding_constraint(intent: TripIntent, search: SearchFn) -> PlanResult:
    """Why is nothing feasible? Relax one hard constraint at a time; the first
    relaxation that yields results names the constraint actually blocking.

    Cheap at two or three meetings, and it is exactly the answer the traveler
    needs — "move the Denver meeting to 11am" beats "no results".
    """
    without_no_fly = [c for c in HARD_CHECKERS if c is not check_no_fly]
    if _feasible(intent, search, without_no_fly):
        blocked = next(
            (
                violation
                for itinerary in _feasible(intent, search, without_no_fly)
                for violation in check_no_fly(itinerary, intent)
            ),
            None,
        )
        return PlanResult(
            binding_constraint=blocked
            or Violation(
                kind="no_fly", severity="hard",
                message="A virtual meeting overlaps every workable flight.",
            ),
            relaxation=(
                "Mark that call flexible, or move it outside the flight window."
            ),
        )

    if _feasible(intent, search, []):
        first = min(intent.in_person(), key=lambda m: m.starts_at, default=None)
        return PlanResult(
            binding_constraint=Violation(
                kind="presence",
                severity="hard",
                meeting_id=(first.id or None) if first else None,
                message=(
                    "No flight arrives early enough to make "
                    f"{first.title!r} in {first.city}." if first
                    else "The meeting times cannot be reached by any flight."
                ),
            ),
            relaxation=(
                "Move the earliest meeting later, allow an overnight the day "
                "before, or attend that one remotely."
            ),
        )

    return PlanResult(
        binding_constraint=Violation(
            kind="no_flights",
            severity="hard",
            message="No flights were returned for one or more legs of this route.",
        ),
        relaxation="Try nearby airports or different dates.",
    )


def solve(intent: TripIntent, search: SearchFn) -> PlanResult:
    itineraries = _feasible(intent, search, HARD_CHECKERS)
    if not itineraries:
        return _binding_constraint(intent, search)

    for itinerary in itineraries:
        itinerary.soft_violations = [
            violation
            for checker in SOFT_CHECKERS
            for violation in checker(itinerary, intent)
        ]
    return PlanResult(itineraries=itineraries)
```

- [ ] **Step 4: Run the tests**

Run: `cd api && .venv/Scripts/python.exe -m pytest tests/test_planning_solver.py -v`
Expected: PASS (14 tests). If `test_solve_with_no_in_person_meetings_plans_no_travel` fails, `city_sequence` is appending the origin twice for a virtual-only trip — the `len(cities) == 1` early return handles it.

- [ ] **Step 5: Remove the unused `Meeting` import if ruff flags it**

Run: `cd api && .venv/Scripts/python.exe -m ruff check .`
Expected: no findings. `Meeting` is imported in `solver.py` only if used; drop it from the import line if ruff reports F401.

- [ ] **Step 6: Commit**

```bash
git add api/planning/solver.py api/tests/test_planning_solver.py
git commit -m "feat(planning): constraint solver with binding-constraint diagnosis"
```

---

### Task 7: AI layers — interpret, judge, risk

Three thin modules, each with a deterministic fallback. This is the task where the invariant gets enforced in code: `judge` validates every id the model returns against the ids the solver produced.

**Files:**
- Create: `api/planning/interpret.py`, `api/planning/judge.py`, `api/planning/risk.py`
- Test: `api/tests/test_planning_ai.py`

**Interfaces:**
- Consumes: Task 4 models, Task 5 `GROUND_BUFFER`.
- Produces:
  - `interpret(text: str, today: date) -> TripIntentDraft` and `class TripIntentDraft(BaseModel)` with `origin_city: str | None`, `meetings: list[MeetingDraft]`, `unresolved: list[str]`
  - `judge(itineraries: list[Itinerary], intent: TripIntent) -> list[Ranking]`
  - `risk_factors(itinerary, intent) -> list[RiskFactor]` and `assess(itinerary, intent) -> RiskAssessment`
  Task 8 calls `interpret`, `judge`, `assess`.

- [ ] **Step 1: Write the failing tests**

Create `api/tests/test_planning_ai.py`:

```python
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from planning.interpret import TripIntentDraft, interpret
from planning.judge import judge
from planning.models import Itinerary, Leg, Meeting, Ranking, TripIntent
from planning.risk import assess, risk_factors

UTC = timezone.utc


def at(day, hour, minute=0):
    return datetime(2026, 9, day, hour, minute, tzinfo=UTC)


def leg(origin="SFO", dest="ORD", depart=None, hours=4, price=30000, stops=0):
    depart = depart or at(1, 9)
    return Leg(
        origin=origin, destination=dest, depart_at=depart,
        arrive_at=depart + timedelta(hours=hours), airline="United",
        fare_class="economy", price_cents=price, stops=stops,
    )


def itinerary(iid, legs=None, price=30000):
    built = Itinerary.from_legs(legs or [leg(price=price)])
    built.id = iid
    return built


# --- judge ----------------------------------------------------------------

@patch("planning.judge._model")
def test_judge_returns_the_models_ranking_when_every_id_is_real(mock_model):
    options = [itinerary("a"), itinerary("b")]
    mock_model.return_value.invoke.return_value = MagicMock(rankings=[
        Ranking(itinerary_id="b", rank=1, rationale="Cheaper and earlier"),
        Ranking(itinerary_id="a", rank=2, rationale="Backup"),
    ])

    result = judge(options, TripIntent(origin_city="SFO"))

    assert [r.itinerary_id for r in result] == ["b", "a"]


@patch("planning.judge._model")
def test_judge_refuses_a_ranking_that_names_an_itinerary_we_never_produced(mock_model):
    """The same lesson as the Duffel offer cache: a model referencing an id
    the server never issued is not a ranking, it's an invention."""
    options = [itinerary("a")]
    mock_model.return_value.invoke.return_value = MagicMock(rankings=[
        Ranking(itinerary_id="does-not-exist", rank=1, rationale="Best value"),
    ])

    result = judge(options, TripIntent(origin_city="SFO"))

    assert [r.itinerary_id for r in result] == ["a"]         # deterministic fallback
    assert mock_model.return_value.invoke.call_count == 2    # one retry, then fall back


@patch("planning.judge._model")
def test_judge_falls_back_to_price_order_when_the_model_raises(mock_model):
    """A misbehaving model degrades output quality; it never 500s the plan."""
    mock_model.return_value.invoke.side_effect = RuntimeError("overloaded")
    options = [itinerary("expensive", price=90000), itinerary("cheap", price=20000)]

    result = judge(options, TripIntent(origin_city="SFO"))

    assert [r.itinerary_id for r in result] == ["cheap", "expensive"]
    assert result[0].rank == 1
    assert result[0].rationale


def test_judge_short_circuits_a_single_itinerary_without_calling_a_model():
    """Nothing to weigh against anything. Paying for a model call to rank one
    option is exactly the decorative AI this project pivoted away from."""
    with patch("planning.judge._model") as mock_model:
        result = judge([itinerary("only")], TripIntent(origin_city="SFO"))
    mock_model.assert_not_called()
    assert [r.itinerary_id for r in result] == ["only"]


# --- risk -----------------------------------------------------------------

def test_risk_factors_flag_a_late_arrival_and_an_early_start():
    plan = itinerary("a", [leg(depart=at(1, 19), hours=5)])   # lands 00:00
    intent = TripIntent(origin_city="SFO", meetings=[
        Meeting(id="m", title="Standup", city="ORD", mode="in_person",
                starts_at=at(2, 7), ends_at=at(2, 8))
    ])

    codes = {factor.code for factor in risk_factors(plan, intent)}

    assert "late_arrival" in codes
    assert "early_start" in codes


def test_risk_factors_flag_a_tight_connection_to_the_meeting():
    plan = itinerary("a", [leg(depart=at(1, 8), hours=4)])    # lands 12:00
    intent = TripIntent(origin_city="SFO", meetings=[
        Meeting(id="m", title="Pitch", city="ORD", mode="in_person",
                starts_at=at(1, 14), ends_at=at(1, 15))
    ])

    codes = {factor.code for factor in risk_factors(plan, intent)}

    assert "tight_ground" in codes


def test_risk_factors_flag_multiple_stops():
    plan = itinerary("a", [leg(stops=2)])
    assert "connections" in {f.code for f in risk_factors(plan, TripIntent(origin_city="SFO"))}


def test_a_clean_itinerary_produces_low_risk_with_no_model_call():
    """No factors means nothing to synthesise. Paying a model to say nothing
    is wrong is the kind of thing this design exists to avoid."""
    plan = itinerary("a", [leg(depart=at(1, 9), hours=4)])    # lands 13:00
    intent = TripIntent(origin_city="SFO", meetings=[
        Meeting(id="m", title="Dinner", city="ORD", mode="in_person",
                starts_at=at(1, 19), ends_at=at(1, 21))
    ])

    with patch("planning.risk._model") as mock_model:
        assessment = assess(plan, intent)

    mock_model.assert_not_called()
    assert assessment.severity == "low"
    assert assessment.factors == []


@patch("planning.risk._model")
def test_assess_synthesises_factors_into_an_advisory(mock_model):
    from planning.models import RiskAssessment

    mock_model.return_value.invoke.return_value = RiskAssessment(
        severity="high",
        advisory="Lands after midnight with a 7am start.",
        recommendations=["Book the airport hotel, not downtown."],
    )
    plan = itinerary("a", [leg(depart=at(1, 19), hours=5)])
    intent = TripIntent(origin_city="SFO", meetings=[
        Meeting(id="m", title="Standup", city="ORD", mode="in_person",
                starts_at=at(2, 7), ends_at=at(2, 8))
    ])

    assessment = assess(plan, intent)

    assert assessment.severity == "high"
    assert assessment.recommendations
    # factors travel with the advisory so a wrong severity is visibly wrong
    assert {f.code for f in assessment.factors} >= {"late_arrival", "early_start"}


@patch("planning.risk._model")
def test_assess_degrades_to_medium_when_the_model_fails(mock_model):
    mock_model.return_value.invoke.side_effect = RuntimeError("overloaded")
    plan = itinerary("a", [leg(depart=at(1, 19), hours=5)])
    intent = TripIntent(origin_city="SFO", meetings=[
        Meeting(id="m", title="Standup", city="ORD", mode="in_person",
                starts_at=at(2, 7), ends_at=at(2, 8))
    ])

    assessment = assess(plan, intent)

    assert assessment.severity == "medium"     # factors exist, synthesis didn't
    assert assessment.factors


# --- interpret ------------------------------------------------------------

@patch("planning.interpret._model")
def test_interpret_returns_a_draft_the_traveler_confirms(mock_model):
    mock_model.return_value.invoke.return_value = TripIntentDraft(
        origin_city="SFO",
        meetings=[Meeting(title="Client pitch", city="ORD", mode="in_person",
                          starts_at=at(1, 19), ends_at=at(1, 20))],
    )

    draft = interpret("Chicago Tuesday 2pm for a client pitch", date(2026, 8, 25))

    assert draft.meetings[0].city == "ORD"
    assert draft.unresolved == []


@patch("planning.interpret._model")
def test_interpret_moves_an_unusable_meeting_to_unresolved_rather_than_guessing(mock_model):
    """A guessed city books a real ticket to the wrong place. The draft says
    'I couldn't tell' and the traveler fills it in."""
    mock_model.return_value.invoke.return_value = TripIntentDraft(
        origin_city="SFO",
        meetings=[Meeting(title="Client pitch", city="ORD", mode="in_person",
                          starts_at=at(1, 19), ends_at=at(1, 20))],
        unresolved=["Couldn't tell which city 'the usual place' means"],
    )

    draft = interpret("meet at the usual place Tuesday", date(2026, 8, 25))

    assert draft.unresolved


@patch("planning.interpret._model")
def test_interpret_returns_an_empty_draft_when_the_model_fails(mock_model):
    mock_model.return_value.invoke.side_effect = RuntimeError("overloaded")

    draft = interpret("anything", date(2026, 8, 25))

    assert draft.meetings == []
    assert draft.unresolved      # says so, rather than silently returning nothing
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd api && .venv/Scripts/python.exe -m pytest tests/test_planning_ai.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'planning.interpret'`.

- [ ] **Step 3: Write `judge.py`**

Create `api/planning/judge.py`:

```python
"""Rank the feasible set and say why.

Everything numeric — totals, policy, soft violations — arrives as a *fact*
computed by code. The model weighs trade-offs and explains them; it does not
recompute them, and it cannot introduce an option the solver didn't produce.

The id validation is the Duffel offer-cache lesson generalised: a model
referencing an id the server never issued is not an answer, it's an invention.
"""
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel

from core.config import settings
from planning.models import Itinerary, Ranking, TripIntent

_PROMPT = (
    "You are Wayfare's trip planner. Every itinerary below already satisfies "
    "the traveler's hard constraints — you are choosing between valid options, "
    "not checking them. Rank them best-first for this traveler, and for each "
    "one give a one-sentence rationale in terms of their own stated "
    "constraints, plus any concerns worth flagging. Weigh cost, timing, "
    "comfort and the listed policy/budget flags against each other. "
    "Use only the itinerary ids given to you."
)


class Rankings(BaseModel):
    rankings: list[Ranking]


def _model():
    return ChatAnthropic(
        model="claude-sonnet-5", api_key=settings.anthropic_api_key
    ).with_structured_output(Rankings)


def _by_price(itineraries: list[Itinerary]) -> list[Ranking]:
    """Deterministic fallback. Cheapest first, honestly labelled — a degraded
    ranking beats a 500, and pretending a model reasoned about it would be
    worse than either."""
    return [
        Ranking(
            itinerary_id=itinerary.id,
            rank=i + 1,
            rationale=f"${itinerary.total_price_cents / 100:,.0f} total.",
            concerns=[v.message for v in itinerary.soft_violations],
        )
        for i, itinerary in enumerate(
            sorted(itineraries, key=lambda x: x.total_price_cents)
        )
    ]


def _describe(itinerary: Itinerary) -> dict:
    return {
        "itinerary_id": itinerary.id,
        "total_price_cents": itinerary.total_price_cents,
        "legs": [
            {
                "route": f"{leg.origin}->{leg.destination}",
                "depart_at": leg.depart_at.isoformat(),
                "arrive_at": leg.arrive_at.isoformat(),
                "airline": leg.airline,
                "fare_class": leg.fare_class,
                "stops": leg.stops,
                "price_cents": leg.price_cents,
            }
            for leg in itinerary.legs
        ],
        "flags": [v.message for v in itinerary.soft_violations],
    }


def judge(itineraries: list[Itinerary], intent: TripIntent) -> list[Ranking]:
    if len(itineraries) <= 1:
        # Nothing to weigh against anything.
        return _by_price(itineraries)

    known = {itinerary.id for itinerary in itineraries}
    payload = {
        "origin_city": intent.origin_city,
        "preferences": intent.preferences,
        "budget_cents": intent.budget_cents,
        "meetings": [
            {
                "title": m.title, "city": m.city, "mode": m.mode,
                "starts_at": m.starts_at.isoformat(), "flexible": m.flexible,
            }
            for m in intent.meetings
        ],
        "itineraries": [_describe(i) for i in itineraries],
    }

    model = _model()
    for _ in range(2):   # one retry: a schema slip is usually not repeated
        try:
            result = model.invoke(
                [{"role": "system", "content": _PROMPT},
                 {"role": "user", "content": str(payload)}]
            )
        except Exception:  # noqa: BLE001 — any model failure degrades, never raises
            break
        rankings = list(result.rankings)
        if rankings and all(r.itinerary_id in known for r in rankings):
            return sorted(rankings, key=lambda r: r.rank)

    return _by_price(itineraries)
```

- [ ] **Step 4: Write `risk.py`**

Create `api/planning/risk.py`:

```python
"""Duty-of-care risk, derived from the itinerary itself.

Code extracts the factors; the model turns them into a severity and a concrete
recommendation. The factors ride along with the advisory so the assessment is
auditable — a wrong severity next to its evidence is visibly wrong, which is
more than could be said for the destination-hash placeholder this replaces.

No external risk feed. Everything here is a mechanical property of the plan.
"""
from datetime import timedelta

from langchain_anthropic import ChatAnthropic

from core.config import settings
from planning.checkers import GROUND_BUFFER
from planning.models import Itinerary, RiskAssessment, RiskFactor, TripIntent

_LATE_ARRIVAL_FROM, _LATE_ARRIVAL_TO = 23, 5
_EARLY_START_BEFORE = 8
_TIGHT_GROUND = timedelta(minutes=60)

_PROMPT = (
    "You are Wayfare's duty-of-care analyst. Given the mechanical risk factors "
    "of a trip, give an overall severity (low/medium/high) and a short "
    "advisory naming the specific factors, plus concrete recommendations the "
    "traveler can act on. Do not invent factors that are not listed."
)


def _model():
    return ChatAnthropic(
        model="claude-sonnet-5", api_key=settings.anthropic_api_key
    ).with_structured_output(RiskAssessment)


def risk_factors(itinerary: Itinerary, intent: TripIntent) -> list[RiskFactor]:
    factors: list[RiskFactor] = []

    for leg in itinerary.legs:
        hour = leg.arrive_at.hour
        if hour >= _LATE_ARRIVAL_FROM or hour < _LATE_ARRIVAL_TO:
            factors.append(RiskFactor(
                code="late_arrival",
                detail=f"Lands in {leg.destination} at {leg.arrive_at:%H:%M} local.",
            ))
        if leg.depart_at.hour >= 22 or leg.depart_at.hour < 5:
            factors.append(RiskFactor(
                code="red_eye",
                detail=f"Departs {leg.origin} at {leg.depart_at:%H:%M} local.",
            ))
        if leg.stops >= 2:
            factors.append(RiskFactor(
                code="connections",
                detail=f"{leg.stops} connections on {leg.origin}→{leg.destination}.",
            ))

    dates = [leg.depart_at.date() for leg in itinerary.legs]
    if len(dates) != len(set(dates)):
        factors.append(RiskFactor(
            code="same_day_city_change",
            detail="Two flights on the same day.",
        ))

    for meeting in intent.in_person():
        if meeting.starts_at.hour < _EARLY_START_BEFORE:
            factors.append(RiskFactor(
                code="early_start",
                detail=f"{meeting.title!r} starts at {meeting.starts_at:%H:%M} local.",
            ))
        arrivals = [
            leg.arrive_at for leg in itinerary.legs
            if leg.destination == meeting.city and leg.arrive_at <= meeting.starts_at
        ]
        if arrivals and meeting.starts_at - max(arrivals) < GROUND_BUFFER + _TIGHT_GROUND:
            factors.append(RiskFactor(
                code="tight_ground",
                detail=(
                    f"Under an hour of slack between landing and "
                    f"{meeting.title!r}."
                ),
            ))
        # No hotel is booked by the planner (Duffel Stays isn't integrated), so
        # an overnight shows up here as something the traveler must arrange.
        if arrivals and max(arrivals).date() < meeting.starts_at.date():
            factors.append(RiskFactor(
                code="overnight_gap",
                detail=f"Overnight in {meeting.city} before {meeting.title!r}; no hotel booked.",
            ))

    return factors


def assess(itinerary: Itinerary, intent: TripIntent) -> RiskAssessment:
    factors = risk_factors(itinerary, intent)
    if not factors:
        return RiskAssessment(severity="low", advisory="No risk factors identified.")

    try:
        assessment = _model().invoke(
            [{"role": "system", "content": _PROMPT},
             {"role": "user", "content": str([f.model_dump() for f in factors])}]
        )
    except Exception:  # noqa: BLE001 — degrade, never raise
        return RiskAssessment(
            severity="medium",
            advisory="Risk factors were identified but could not be summarised.",
            factors=factors,
        )

    assessment.factors = factors   # code's factors win; the model only summarises
    return assessment
```

- [ ] **Step 5: Write `interpret.py`**

Create `api/planning/interpret.py`:

```python
"""Prose (or a pasted invite) -> a *draft* set of meetings.

Draft is the whole point. The output populates the meeting form and the
traveler confirms it; nothing is solved or booked from an uninspected model
reading. Making someone type structured data as prose so a model can parse it
back would be a form with extra latency and a failure mode — the form is the
primary path and this is the accelerant for input that arrives messy.

Anything ambiguous lands in `unresolved` rather than being guessed. A guessed
city books a real ticket to the wrong place.
"""
from datetime import date

from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field

from core.config import settings
from planning.models import Meeting

_PROMPT = (
    "Extract business meetings from the text into structured form. Today is "
    "{today}; resolve relative dates against it. Use IATA airport codes for "
    "cities (Chicago -> ORD, Denver -> DEN, San Francisco -> SFO). Mark a "
    "meeting in_person only when the text says or clearly implies the traveler "
    "must physically attend; otherwise virtual. Mark flexible only when the "
    "text says it can be moved, skipped, or taken from anywhere. "
    "Every meeting needs a timezone-aware start and end. "
    "If anything is ambiguous — an unclear city, a date you cannot resolve, a "
    "missing time — do NOT guess: describe what you could not determine in "
    "`unresolved` and leave that meeting out."
)


class TripIntentDraft(BaseModel):
    origin_city: str | None = None
    meetings: list[Meeting] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)


def _model():
    return ChatAnthropic(
        model="claude-sonnet-5", api_key=settings.anthropic_api_key
    ).with_structured_output(TripIntentDraft)


def interpret(text: str, today: date) -> TripIntentDraft:
    try:
        return _model().invoke(
            [{"role": "system", "content": _PROMPT.format(today=today.isoformat())},
             {"role": "user", "content": text}]
        )
    except Exception:  # noqa: BLE001 — say so, rather than silently returning nothing
        return TripIntentDraft(
            unresolved=["Could not read the description — add the meetings manually."]
        )
```

- [ ] **Step 6: Run the tests and lint**

Run: `cd api && .venv/Scripts/python.exe -m pytest tests/test_planning_ai.py -v && .venv/Scripts/python.exe -m ruff check .`
Expected: PASS (12 tests), no lint findings.

- [ ] **Step 7: Commit**

```bash
git add api/planning/interpret.py api/planning/judge.py api/planning/risk.py api/tests/test_planning_ai.py
git commit -m "feat(planning): interpret, judge and risk layers with deterministic fallbacks"
```

---

### Task 8: Planning routes

**Files:**
- Create: `api/routes/planning.py`
- Modify: `api/main.py`
- Test: `api/tests/test_routes_planning.py`

**Interfaces:**
- Consumes: Tasks 4–7; `search_travel`/`create_booking` from `api/agent/tools.py`; `get_db`.
- Produces: `router` in `api/routes/planning.py` with
  `POST /trips`, `GET|POST /trips/{trip_id}/meetings`, `DELETE /meetings/{meeting_id}`,
  `POST /trips/{trip_id}/interpret`, `POST /trips/{trip_id}/plan`,
  `POST /itineraries/{itinerary_id}/select`.
  Also `build_intent(db, trip_id) -> TripIntent` (used by plan and select).
  Task 9 (the UI) calls all of these.

- [ ] **Step 1: Write the failing tests**

Create `api/tests/test_routes_planning.py`:

```python
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from main import app
from planning.models import Itinerary, Leg, PlanResult, Ranking, RiskAssessment

client = TestClient(app)
UTC = timezone.utc

TRIP = {
    "id": "trip-1", "employee_id": "emp-1", "company_id": "co-1",
    "origin_city": "SFO", "budget_cents": 200000,
}
MEETING = {
    "id": "m1", "trip_id": "trip-1", "title": "Client pitch", "city": "ORD",
    "mode": "in_person", "flexible": False,
    "starts_at": "2026-09-01T14:00:00-05:00",
    "ends_at": "2026-09-01T15:00:00-05:00",
}
RULES = {
    "max_fare_class": "economy",
    "max_hotel_nightly_rate_cents": 25000,
    "approval_threshold_cents": 150000,
}


def _leg(price=30000):
    depart = datetime(2026, 9, 1, 6, tzinfo=UTC)
    return Leg(
        origin="SFO", destination="ORD", depart_at=depart,
        arrive_at=depart + timedelta(hours=4), airline="United",
        fare_class="economy", price_cents=price, offer_id="off_1",
    )


def _db(**tables):
    """Minimal Supabase-client double. `tables` maps table name -> rows
    returned by any select on it."""
    db = MagicMock()

    def table(name):
        handle = MagicMock()
        rows = tables.get(name, [])
        handle.select.return_value.eq.return_value.execute.return_value.data = rows
        handle.select.return_value.eq.return_value.order.return_value.execute.return_value.data = rows
        handle.insert.return_value.execute.return_value.data = rows or [{"id": "new-1"}]
        handle.update.return_value.eq.return_value.execute.return_value.data = rows
        handle.delete.return_value.eq.return_value.execute.return_value.data = rows
        return handle

    db.table.side_effect = table
    return db


# --- trips / meetings -----------------------------------------------------

@patch("routes.planning.get_db")
def test_create_trip_resolves_the_company_server_side(mock_get_db):
    """The client sends an employee id; company_id is never taken from the
    request — that would be an IDOR waiting to happen."""
    mock_get_db.return_value = _db(employees=[{"company_id": "co-1"}], trips=[{"id": "trip-9"}])

    response = client.post("/trips", json={"employee_id": "emp-1", "origin_city": "SFO"})

    assert response.status_code == 200
    assert response.json()["id"] == "trip-9"
    inserted = mock_get_db.return_value.table("trips").insert.call_args[0][0]
    assert inserted["company_id"] == "co-1"
    assert inserted["thread_id"]


@patch("routes.planning.get_db")
def test_create_trip_404s_for_an_unknown_employee(mock_get_db):
    mock_get_db.return_value = _db(employees=[])
    assert client.post("/trips", json={"employee_id": "nope"}).status_code == 404


@patch("routes.planning.get_db")
def test_add_meetings_rejects_an_in_person_meeting_with_no_city(mock_get_db):
    """Validated at the boundary, mirroring the DB check constraint, so the
    error is readable instead of a 500 from Postgres."""
    mock_get_db.return_value = _db(trips=[TRIP])

    response = client.post("/trips/trip-1/meetings", json={"meetings": [{
        "title": "Pitch", "mode": "in_person",
        "starts_at": "2026-09-01T14:00:00-05:00",
        "ends_at": "2026-09-01T15:00:00-05:00",
    }]})

    assert response.status_code == 422


# --- plan -----------------------------------------------------------------

@patch("routes.planning.assess")
@patch("routes.planning.judge")
@patch("routes.planning.solve")
@patch("routes.planning.get_db")
def test_plan_persists_itineraries_and_returns_them_ranked(
    mock_get_db, mock_solve, mock_judge, mock_assess
):
    mock_get_db.return_value = _db(
        trips=[TRIP], meetings=[MEETING], employees=[{"travel_preferences": {}}],
        policies=[{"id": "pol-1", "rules": RULES}],
        itineraries=[{"id": "it-1"}],
    )
    mock_solve.return_value = PlanResult(itineraries=[Itinerary.from_legs([_leg()])])
    mock_judge.return_value = [Ranking(itinerary_id="it-1", rank=1, rationale="Cheapest")]
    mock_assess.return_value = RiskAssessment(severity="low", advisory="Fine")

    response = client.post("/trips/trip-1/plan")

    assert response.status_code == 200
    body = response.json()
    assert len(body["itineraries"]) == 1
    assert body["itineraries"][0]["rationale"] == "Cheapest"
    assert body["itineraries"][0]["risk"]["severity"] == "low"
    # ids come from the persisted rows, never from the model
    assert body["itineraries"][0]["id"] == "it-1"


@patch("routes.planning.solve")
@patch("routes.planning.get_db")
def test_plan_returns_the_binding_constraint_instead_of_an_empty_list(
    mock_get_db, mock_solve
):
    """'No results' is the one answer a traveler can do nothing with."""
    from planning.models import Violation

    mock_get_db.return_value = _db(
        trips=[TRIP], meetings=[MEETING], employees=[{"travel_preferences": {}}],
        policies=[{"id": "pol-1", "rules": RULES}],
    )
    mock_solve.return_value = PlanResult(
        binding_constraint=Violation(
            kind="presence", severity="hard",
            message="No flight arrives early enough.",
        ),
        relaxation="Move the meeting later.",
    )

    body = client.post("/trips/trip-1/plan").json()

    assert body["itineraries"] == []
    assert body["binding_constraint"]["kind"] == "presence"
    assert body["relaxation"]


@patch("routes.planning.get_db")
def test_plan_404s_when_the_trip_has_no_meetings(mock_get_db):
    mock_get_db.return_value = _db(
        trips=[TRIP], meetings=[], employees=[{"travel_preferences": {}}],
        policies=[{"id": "pol-1", "rules": RULES}],
    )
    assert client.post("/trips/trip-1/plan").status_code == 400


# --- select / reprice -----------------------------------------------------

@patch("routes.planning._search_flights")
@patch("routes.planning.get_db")
def test_select_asks_for_confirmation_when_the_price_went_up(
    mock_get_db, mock_search
):
    """Any increase, not a percentage band: silently charging more than the
    displayed price is not a thing to tune."""
    stored = {
        "id": "it-1", "trip_id": "trip-1",
        "legs": [_leg(price=30000).model_dump(mode="json")],
        "total_price_cents": 30000,
    }
    mock_get_db.return_value = _db(itineraries=[stored], trips=[TRIP],
                                   policies=[{"id": "pol-1", "rules": RULES}])
    mock_search.return_value = [{
        "id": "off_new", "airline": "United", "fare_class": "economy",
        "origin": "SFO", "destination": "ORD", "depart_date": "2026-09-01",
        "price_cents": 41000, "depart_at": _leg().depart_at.isoformat(),
        "arrive_at": _leg().arrive_at.isoformat(), "stops": 0,
    }]

    body = client.post("/itineraries/it-1/select", json={}).json()

    assert body["status"] == "reprice_required"
    assert body["itinerary"]["total_price_cents"] == 41000


@patch("routes.planning.create_booking")
@patch("routes.planning._search_flights")
@patch("routes.planning.get_db")
def test_select_books_straight_through_when_the_price_held(
    mock_get_db, mock_search, mock_create_booking
):
    stored = {
        "id": "it-1", "trip_id": "trip-1",
        "legs": [_leg(price=30000).model_dump(mode="json")],
        "total_price_cents": 30000,
    }
    mock_get_db.return_value = _db(itineraries=[stored], trips=[TRIP],
                                   policies=[{"id": "pol-1", "rules": RULES}])
    mock_search.return_value = [{
        "id": "off_fresh", "airline": "United", "fare_class": "economy",
        "origin": "SFO", "destination": "ORD", "depart_date": "2026-09-01",
        "price_cents": 30000, "depart_at": _leg().depart_at.isoformat(),
        "arrive_at": _leg().arrive_at.isoformat(), "stops": 0,
    }]
    mock_create_booking.return_value = {"id": "bk-1", "status": "booked", "violations": []}

    body = client.post("/itineraries/it-1/select", json={}).json()

    assert body["status"] == "booked"
    assert body["bookings"][0]["id"] == "bk-1"
    # booked from the FRESH offer id, never the stored one
    booked_details = mock_create_booking.call_args[0][2]
    assert booked_details["id"] == "off_fresh"


@patch("routes.planning._search_flights")
@patch("routes.planning.get_db")
def test_select_refuses_when_a_leg_no_longer_exists(mock_get_db, mock_search):
    stored = {
        "id": "it-1", "trip_id": "trip-1",
        "legs": [_leg().model_dump(mode="json")],
        "total_price_cents": 30000,
    }
    mock_get_db.return_value = _db(itineraries=[stored], trips=[TRIP],
                                   policies=[{"id": "pol-1", "rules": RULES}])
    mock_search.return_value = []

    body = client.post("/itineraries/it-1/select", json={}).json()

    assert body["status"] == "reprice_required"
    assert body["unavailable"]


@patch("routes.planning.get_db")
def test_select_404s_for_an_itinerary_we_never_issued(mock_get_db):
    """Same rule as the offer cache: selection references something the
    server produced, or it doesn't happen."""
    mock_get_db.return_value = _db(itineraries=[])
    assert client.post("/itineraries/made-up/select", json={}).status_code == 404
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd api && .venv/Scripts/python.exe -m pytest tests/test_routes_planning.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'routes.planning'`.

- [ ] **Step 3: Write the routes**

Create `api/routes/planning.py`:

```python
"""Constraint-planner endpoints.

Shape of the flow: meetings go in (typed on a form, or drafted by `interpret`
and confirmed), `solve` produces the feasible set, the AI layers rank and
assess it, and the result is persisted before it is returned — so selection
later references a plan this server issued rather than one a client handed
back.
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.tools import create_booking, search_travel
from core.db import get_db
from planning.interpret import interpret
from planning.judge import judge
from planning.models import Itinerary, Leg, Meeting, TripIntent
from planning.risk import assess
from planning.solver import solve

router = APIRouter()


class CreateTrip(BaseModel):
    employee_id: str
    origin_city: str | None = None
    budget_cents: int | None = None


class AddMeetings(BaseModel):
    meetings: list[Meeting]


class InterpretRequest(BaseModel):
    text: str


class SelectRequest(BaseModel):
    confirm_reprice: bool = False


def _search_flights(origin: str, destination: str, date: str) -> list[dict]:
    """Thin seam over the existing tool so tests can inject fares without
    reaching for httpx. `.func` unwraps the LangChain @tool decorator."""
    return search_travel.func("flight", origin, destination, date)


def _trip(db, trip_id: str) -> dict:
    rows = db.table("trips").select("*").eq("id", trip_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Trip not found")
    return rows[0]


def _rules(db, company_id: str) -> dict:
    rows = db.table("policies").select("rules").eq("company_id", company_id).execute().data
    return rows[0]["rules"] if rows else {}


def build_intent(db, trip_id: str) -> TripIntent:
    trip = _trip(db, trip_id)
    meetings = (
        db.table("meetings").select("*").eq("trip_id", trip_id).execute().data
    )
    employees = (
        db.table("employees").select("travel_preferences").eq("id", trip["employee_id"]).execute().data
    )
    preferences = (employees[0].get("travel_preferences") if employees else None) or {}
    return TripIntent(
        origin_city=trip.get("origin_city") or "SFO",
        meetings=[Meeting(**m) for m in meetings],
        budget_cents=trip.get("budget_cents"),
        preferences=preferences,
        policy_rules=_rules(db, trip["company_id"]),
    )


@router.post("/trips")
def create_trip(body: CreateTrip) -> dict:
    db = get_db()
    employees = (
        db.table("employees").select("company_id").eq("id", body.employee_id).execute().data
    )
    if not employees:
        raise HTTPException(status_code=404, detail="Employee not found")

    row = db.table("trips").insert({
        "company_id": employees[0]["company_id"],   # resolved server-side, never from the request
        "employee_id": body.employee_id,
        "thread_id": str(uuid.uuid4()),
        "origin_city": body.origin_city,
        "budget_cents": body.budget_cents,
    }).execute().data[0]
    return {"id": row["id"]}


@router.get("/trips/{trip_id}/meetings")
def list_meetings(trip_id: str) -> list[dict]:
    return get_db().table("meetings").select("*").eq("trip_id", trip_id).execute().data


@router.post("/trips/{trip_id}/meetings")
def add_meetings(trip_id: str, body: AddMeetings) -> list[dict]:
    db = get_db()
    _trip(db, trip_id)
    rows = [
        {
            "trip_id": trip_id,
            "title": m.title,
            "city": m.city,
            "mode": m.mode,
            "starts_at": m.starts_at.isoformat(),
            "ends_at": m.ends_at.isoformat(),
            "flexible": m.flexible,
        }
        for m in body.meetings
    ]
    return db.table("meetings").insert(rows).execute().data


@router.delete("/meetings/{meeting_id}")
def delete_meeting(meeting_id: str) -> dict:
    get_db().table("meetings").delete().eq("id", meeting_id).execute()
    return {"ok": True}


@router.post("/trips/{trip_id}/interpret")
def interpret_trip(trip_id: str, body: InterpretRequest) -> dict:
    """Returns a DRAFT. Persists nothing — the traveler confirms it into
    meetings, which is what makes this an accelerant rather than a model
    quietly deciding where someone flies."""
    draft = interpret(body.text, datetime.now(UTC).date())
    return draft.model_dump(mode="json")


@router.post("/trips/{trip_id}/plan")
def plan_trip(trip_id: str) -> dict:
    db = get_db()
    intent = build_intent(db, trip_id)
    if not intent.meetings:
        raise HTTPException(
            status_code=400, detail="Add at least one meeting before planning."
        )

    result = solve(intent, lambda o, d, day: [
        __import__("travel.models", fromlist=["FlightOption"]).FlightOption(**f)
        for f in _search_flights(o, d, day) if "error" not in f
    ])
    if not result.itineraries:
        return {
            "itineraries": [],
            "binding_constraint": (
                result.binding_constraint.model_dump() if result.binding_constraint else None
            ),
            "relaxation": result.relaxation,
        }

    # Persist first, so every id the AI layers see is one this server issued.
    stored = db.table("itineraries").insert([
        {
            "trip_id": trip_id,
            "legs": [leg.model_dump(mode="json") for leg in i.legs],
            "total_price_cents": i.total_price_cents,
            "soft_violations": [v.model_dump() for v in i.soft_violations],
        }
        for i in result.itineraries
    ]).execute().data

    for itinerary, row in zip(result.itineraries, stored, strict=True):
        itinerary.id = row["id"]

    rankings = {r.itinerary_id: r for r in judge(result.itineraries, intent)}

    out = []
    for itinerary in result.itineraries:
        ranking = rankings.get(itinerary.id)
        risk = assess(itinerary, intent)
        db.table("itineraries").update({
            "rank": ranking.rank if ranking else None,
            "rationale": ranking.rationale if ranking else None,
            "concerns": ranking.concerns if ranking else [],
            "risk": risk.model_dump(mode="json"),
        }).eq("id", itinerary.id).execute()
        out.append({
            "id": itinerary.id,
            "legs": [leg.model_dump(mode="json") for leg in itinerary.legs],
            "total_price_cents": itinerary.total_price_cents,
            "soft_violations": [v.model_dump() for v in itinerary.soft_violations],
            "rank": ranking.rank if ranking else None,
            "rationale": ranking.rationale if ranking else "",
            "concerns": ranking.concerns if ranking else [],
            "risk": risk.model_dump(mode="json"),
        })

    out.sort(key=lambda i: (i["rank"] is None, i["rank"]))
    return {"itineraries": out, "binding_constraint": None, "relaxation": None}


def _reprice(leg: Leg) -> dict | None:
    """Find today's version of a stored leg.

    Plans ride on schedules, which are stable; offers expire within seconds on
    aggregator content. So the stored offer id is a hint and this re-search is
    what actually produces something bookable — matched on carrier and
    departure instant, which is what the traveler agreed to.
    """
    fresh = _search_flights(leg.origin, leg.destination, leg.depart_at.date().isoformat())
    for option in fresh:
        if "error" in option:
            return None
        if option.get("airline") != leg.airline or not option.get("depart_at"):
            continue
        if datetime.fromisoformat(option["depart_at"]) == leg.depart_at:
            return option
    return None


@router.post("/itineraries/{itinerary_id}/select")
def select_itinerary(itinerary_id: str, body: SelectRequest) -> dict:
    db = get_db()
    rows = db.table("itineraries").select("*").eq("id", itinerary_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Itinerary not found")

    stored = rows[0]
    legs = [Leg(**leg) for leg in stored["legs"]]

    priced, unavailable = [], []
    for leg in legs:
        option = _reprice(leg)
        if option is None:
            unavailable.append(f"{leg.origin}→{leg.destination}")
        else:
            priced.append(option)

    if unavailable:
        return {
            "status": "reprice_required",
            "unavailable": unavailable,
            "itinerary": stored,
        }

    total = sum(option["price_cents"] for option in priced)
    if total > stored["total_price_cents"] and not body.confirm_reprice:
        # Any increase, not a percentage band. A decrease books through: nobody
        # needs to consent to paying less.
        return {
            "status": "reprice_required",
            "unavailable": [],
            "itinerary": {**stored, "total_price_cents": total, "legs": priced},
        }

    trip = _trip(db, stored["trip_id"])
    rules = _rules(db, trip["company_id"])
    bookings = [
        create_booking.func(stored["trip_id"], "flight", option, rules)
        for option in priced
    ]

    db.table("itineraries").update({"selected": True}).eq("id", itinerary_id).execute()
    status = (
        "booked"
        if all(b.get("status") == "booked" for b in bookings)
        else "needs_attention"
    )
    return {"status": status, "bookings": bookings, "total_price_cents": total}
```

- [ ] **Step 4: Replace the ugly dynamic import in `plan_trip`**

The `__import__` above is a placeholder for the plan's benefit — replace it. At the top of `api/routes/planning.py` add `from travel.models import FlightOption`, then in `plan_trip` use:

```python
    def search(origin: str, destination: str, day: str):
        return [
            FlightOption(**f)
            for f in _search_flights(origin, destination, day)
            if "error" not in f
        ]

    result = solve(intent, search)
```

- [ ] **Step 5: Register the router**

In `api/main.py`, add the import alongside the others:

```python
from routes.planning import router as planning_router
```

and the registration after `app.include_router(duty_of_care_router)`:

```python
app.include_router(planning_router)
```

- [ ] **Step 6: Run the tests and lint**

Run: `cd api && .venv/Scripts/python.exe -m pytest && .venv/Scripts/python.exe -m ruff check .`
Expected: all pass (existing 62 + the new planning tests), no lint findings.

- [ ] **Step 7: Commit**

```bash
git add api/routes/planning.py api/main.py api/tests/test_routes_planning.py
git commit -m "feat(api): planning endpoints with mandatory reprice at selection"
```

---

### Task 9: Planner UI

**Files:**
- Create: `web/src/app/plan/page.tsx`, `web/src/app/plan/[tripId]/page.tsx`
- Create: `web/src/components/plan/meeting-form.tsx`, `web/src/components/plan/itinerary-card.tsx`
- Modify: `web/src/components/app-shell.tsx` (add the Plan nav item), `web/src/app/home/page.tsx` (entry point)

**Interfaces:**
- Consumes: every endpoint from Task 8.
- Produces: no exported API beyond the two page components and the two view components.

- [ ] **Step 1: `/plan` — start a trip**

Create `web/src/app/plan/page.tsx`. A client component that:
1. Resolves the signed-in employee the way `home/page.tsx` already does
   (`supabaseBrowserClient.auth.getUser()` → `employees` row by `auth_user_id`).
2. Renders a small form: **Home airport** (text, IATA, default `SFO`) and
   **Trip budget** (optional, dollars).
3. On submit, `POST ${API}/trips` with `{employee_id, origin_city, budget_cents}`
   and `router.push(`/plan/${id}`)`.

Use the same API base constant the existing pages use (`process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"` — copy whatever `web/src/app/itinerary/page.tsx` already does; do not introduce a second convention). Wrap the page in `<AppShell title="Plan a trip" meta="Start with where you have to be">`.

- [ ] **Step 2: `web/src/components/plan/meeting-form.tsx`**

A controlled form emitting one meeting:

```tsx
export type MeetingDraft = {
  title: string;
  city: string;
  mode: "in_person" | "virtual";
  starts_at: string;   // datetime-local value
  ends_at: string;
  flexible: boolean;
};
```

Fields: title (text), mode (two radio pills, `in_person` default), city (text,
IATA — **disabled and cleared when mode is `virtual`**), start and end
(`<input type="datetime-local">`), and a "This one can move" checkbox for
`flexible`. Native date inputs, not a picker library.

The submit handler converts each `datetime-local` value to an offset-carrying
ISO string with `new Date(value).toISOString()` before it leaves the browser —
the API rejects naive datetimes, and that rejection is deliberate.

Styling: `rounded-xl border border-[var(--color-line)] bg-white p-5`, labels in
`font-mono text-[11px] uppercase tracking-wide text-[var(--color-slate)]`,
inputs `rounded-lg border border-[var(--color-line)] px-3 py-2 font-sans text-sm`.
Reuse the existing `Button`.

- [ ] **Step 3: `web/src/components/plan/itinerary-card.tsx`**

Renders one planned itinerary:
- Rank badge (`#1`, `#2`) in amber, the total in `font-mono`.
- The legs as a vertical timeline: `SFO → ORD`, `Tue 6:00a — 10:00a`, airline,
  and `Nonstop` / `1 stop`.
- The rationale in `font-sans text-sm text-[var(--color-ink)]`.
- Concerns and `soft_violations` as coral `Badge`s. **A soft violation is shown,
  never hidden** — that is the whole point of it being soft.
- The risk block: severity chip (teal `low` / amber `medium` / coral `high`),
  the advisory, the recommendations as a list, and the raw `risk.factors`
  rendered underneath in `font-mono text-[11px] text-[var(--color-mute)]` so
  the assessment is auditable rather than a black box.
- A "Select and book" button.

- [ ] **Step 4: `/plan/[tripId]` — the planner**

Create `web/src/app/plan/[tripId]/page.tsx`, a client component with four regions:

1. **Paste box** — a textarea plus "Read this for me". Posts to
   `/trips/{id}/interpret` and merges the returned `meetings` into the local
   draft list. Renders `unresolved` entries as an amber note above the list:
   *"Couldn't work these out — add them yourself."* Nothing from the model is
   saved until the traveler presses Save; make that visible in the copy
   ("Drafted from your text — check it before saving").
2. **Meeting list + form** — the local drafts, each removable, plus
   `MeetingForm` to add one. "Save meetings" posts to `/trips/{id}/meetings`.
3. **Plan** — a "Find itineraries" button posting to `/trips/{id}/plan`.
   Show a "Working through your constraints…" state while it runs (it does a
   real search per hop, so it is seconds, not instant).
4. **Results** — either `itineraries.map(ItineraryCard)`, or, when
   `binding_constraint` is present, a coral panel with the constraint's
   `message` as the heading and `relaxation` as the body. Never render an
   empty list with no explanation.

"Select and book" posts to `/itineraries/{id}/select`. On
`status === "reprice_required"` show a confirmation panel with the new total
(`"The fare moved to $X since we planned this."`) and a button that re-posts
with `{confirm_reprice: true}`; on missing legs say which route went away and
offer "Plan again". On `booked`, route to `/itinerary`.

- [ ] **Step 5: Entry points**

In `web/src/components/app-shell.tsx`, add to the `NAV` array (after Home), and
import the icon from `lucide-react`:

```tsx
{ href: "/plan", label: "Plan", icon: CalendarClock },
```

`NAV.slice(1)` in the sidebar already renders everything after Home, so no
other change is needed there.

In `web/src/app/home/page.tsx`, add a "Plan a trip" `Link` styled as a primary
button next to the existing "Review trips" pill, pointing at `/plan`.

- [ ] **Step 6: Build and lint**

Run: `npm run lint --prefix web && npm run build --prefix web`
Expected: both clean. Fix any `bg-[var(--x)]` → `bg-(--x)` canonical-class
warnings the Tailwind plugin raises in files you touched.

- [ ] **Step 7: Manual check**

With `api` and `web` running: sign in, `/plan` → create a trip → paste
*"I need to be in Chicago on the 14th at 2pm for a client pitch, and Denver on
the 16th at 10am. I have a board call on the 15th at 9am I can't miss."* →
confirm the drafted meetings → Find itineraries → confirm plans render with
rationale, concerns and risk → select one → confirm it books or asks to
reprice.

- [ ] **Step 8: Commit**

```bash
git add web/
git commit -m "feat(web): constraint planner UI -- meetings in, ranked plans out"
```

---

### Task 10: Wire the real risk assessment into duty of care, and update docs

The duty-of-care dashboard still hashes the destination string for a risk
level. The planner now produces a real, itinerary-derived assessment; use it
where one exists and keep the honest placeholder where one doesn't.

**Files:**
- Modify: `api/routes/duty_of_care.py`
- Modify: `CLAUDE.md`, `docs/architecture.md`
- Create: `docs/superpowers/plans/2026-07-29-constraint-planner-status.md`
- Test: `api/tests/test_routes_duty_of_care.py`

**Interfaces:**
- Consumes: the `itineraries.risk` column (Task 1) and the assessments written by Task 8.
- Produces: `/duty-of-care` entries gain `risk_source: "itinerary" | "placeholder"`.

- [ ] **Step 1: Write the failing test**

Add to `api/tests/test_routes_duty_of_care.py`:

```python
@patch("routes.duty_of_care.get_db")
def test_duty_of_care_prefers_a_real_itinerary_risk_assessment(mock_get_db):
    """The destination hash was always a placeholder. Where the planner has
    produced a real assessment, that wins -- and the response says which it
    is, so the UI never presents a hash as intelligence."""
    ...   # follow the existing _db double in this file; return one selected
          # itinerary row with risk = {"severity": "high", "advisory": "..."}

    entry = client.get("/duty-of-care").json()[0]

    assert entry["trip"]["risk_level"] == "high"
    assert entry["trip"]["risk_source"] == "itinerary"


@patch("routes.duty_of_care.get_db")
def test_duty_of_care_labels_the_hash_as_a_placeholder(mock_get_db):
    ...   # no itineraries row

    entry = client.get("/duty-of-care").json()[0]

    assert entry["trip"]["risk_source"] == "placeholder"
```

Fill the `...` sections in by copying the existing `_db` double already in
`api/tests/test_routes_duty_of_care.py` and adding an `itineraries` table to it.

- [ ] **Step 2: Run and watch it fail**

Run: `cd api && .venv/Scripts/python.exe -m pytest tests/test_routes_duty_of_care.py -v`
Expected: FAIL — `KeyError: 'risk_source'`.

- [ ] **Step 3: Implement**

In `api/routes/duty_of_care.py`, inside the per-employee loop, after loading
`bookings`:

```python
        selected = (
            db.table("itineraries")
            .select("risk")
            .eq("trip_id", trip["id"])
            .eq("selected", True)
            .execute()
            .data
        )
        assessment = selected[0]["risk"] if selected and selected[0].get("risk") else None
```

and build the trip entry with:

```python
                    "risk_level": assessment["severity"] if assessment else _mock_risk_level(destination),
                    # The hash was never intelligence. Saying which source this
                    # came from is what stops the UI presenting it as one.
                    "risk_source": "itinerary" if assessment else "placeholder",
                    "risk_advisory": assessment.get("advisory") if assessment else None,
```

Update `_mock_risk_level`'s docstring to note it is now the fallback for trips
the planner has not produced an itinerary for.

- [ ] **Step 4: Show the distinction in the UI**

In `web/src/app/duty-of-care/page.tsx`, render `risk_advisory` under the risk
badge when present, and keep the existing "placeholder data" labelling only
for entries where `risk_source === "placeholder"`.

- [ ] **Step 5: Update `CLAUDE.md`**

Replace the `## Architecture` paragraph's final sentence and add a new section
after `## Duffel`:

```markdown
## Planning

The planner (`api/planning/`) is the load-bearing AI surface: meetings in,
ranked itineraries out. `interpret` drafts structured meetings from prose and
the traveler confirms them; `solver.solve` — a pure function with `search`
injected — enumerates itineraries satisfying every hard constraint, or names
the binding constraint when none do; `judge` and `risk` rank and assess only
what the solver produced.

The invariant: **the AI never emits an itinerary code hasn't validated, and
code never guesses at intent.** `judge` validates every itinerary id it gets
back against the ids the solver produced and falls back to price order
otherwise — the same rule as the Duffel offer cache, for the same reason.

Constraints live in `planning/checkers.py` as two lists. Hard means infeasible
and hidden; soft means shown and flagged. Policy is deliberately soft, because
the manager approval path already handles out-of-policy trips and hiding them
would make the planner worse than the chat. Adding international support means
appending `check_visa`/`check_passport_validity` to `HARD_CHECKERS`; nothing
else in the solver changes.

Selection always reprices. Plans ride on *schedules*, which are stable; offers
expire in seconds. Any price increase or missing leg needs explicit
confirmation before booking, and booking still goes through `issue_ticket()`.
```

- [ ] **Step 6: Update `docs/architecture.md`**

Add the planner to the module map and the request flow, matching that
document's existing structure and tone. Read it first; do not restructure it.

- [ ] **Step 7: Write the status doc**

Create `docs/superpowers/plans/2026-07-29-constraint-planner-status.md`
following the shape of `2026-07-28-duffel-integration.md`: **Built**,
**Deliberately not built**, **Follow-ups**. Record specifically:
- the calendar seam (`meetings` table) and the international seam (checker lists)
- that `_stays()` merges repeat visits to one city into a single window
- that hotels are outside the solver, so an overnight is a risk factor, not a booking
- that the chat agent and the planner both exist and are not yet reconciled

- [ ] **Step 8: Full suite, lint, build**

Run:
```bash
cd api && .venv/Scripts/python.exe -m pytest && .venv/Scripts/python.exe -m ruff check .
npm run lint --prefix web && npm run build --prefix web
```
Expected: all green.

- [ ] **Step 9: Commit**

```bash
git add api/ web/ docs/ CLAUDE.md
git commit -m "feat: use itinerary-derived risk in duty of care, document the planner"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| `meetings` / `itineraries` tables, trip + employee columns | 1 |
| `FlightOption` times | 2, 3 |
| Domain models, `flexible` semantics | 4 |
| Pluggable hard/soft checkers, international seam | 5 |
| Solver, presence windows, binding constraint, schedules-not-offers | 6 |
| Interpret / judge / risk, id validation, no-call-when-clean | 7 |
| Endpoints, reprice-at-selection, `issue_ticket` reuse | 8 |
| Planner UI, auditable risk display, infeasibility panel | 9 |
| Risk replaces the destination hash; docs | 10 |
| Calendar / international / real feed / multi-traveler / hotels — out | documented in 10's status doc |

**Type consistency:** `Violation.kind` values used across Tasks 5, 6 and 8 are
`presence | no_fly | budget | policy | red_eye | connections | no_flights`.
`Leg` field names match between `models.py` (Task 4), the solver's `_to_leg`
(Task 6), and the route's `Leg(**leg)` rehydration (Task 8). `Ranking` is
defined once in Task 4 and imported by Task 7's `Rankings` wrapper.
`GROUND_BUFFER`/`AIRPORT_LEAD` are defined in `checkers.py` (Task 5) and
imported by both `solver.py` (Task 6) and `risk.py` (Task 7).

**Known rough edge, deliberately kept:** `_stays()` keys presence windows by
city, so a trip that returns to the same city twice merges both stays. Marked
with a `ponytail:` comment and recorded in the status doc rather than solved
speculatively — the slice targets two or three meetings.
