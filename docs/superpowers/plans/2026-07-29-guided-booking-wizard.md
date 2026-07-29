# Guided Booking Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second, non-chat way to book a trip — a step-by-step guided wizard (Trip basics → Flight → Hotel → Review, with a progress stepper) — alongside the existing chat flow, with a "Plan a trip" entry point (which doesn't exist in the UI today) and a button to switch between the two modes for the same trip at any time.

**Architecture:** No new services. Three new/extended FastAPI endpoints in `api/` call the *same* tool-layer functions (`search_travel`, `check_policy` via `create_booking`) the chat agent already uses — no LLM involved, deterministic and instant. `web/` gets a chooser page, a wizard page, and two small new components; existing pages (Home, Trips, Chat) get small additions to link to/from the new flow.

**Tech Stack:** Same as existing (Python 3.13/FastAPI, LangChain tool functions, Next.js App Router + Tailwind, Supabase). No new dependencies.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-29-guided-booking-wizard-design.md` — implements it in full. Explicitly deferred (per spec, confirmed with user): no step-resumption when switching modes on a trip that already has bookings, and the chat agent is not told about bookings the wizard already made.
- `api/` remains the only place that calls Claude/Duffel/Voyage — the new wizard endpoints call existing tool-layer Python functions directly, never the LLM.
- Reuse existing tool-layer functions (`search_travel`, `create_booking` in `api/agent/tools.py`) exactly as they are — do not duplicate their logic in the new routes.
- Every task must leave the repo in a state where `git status` is clean after its own commit.
- Frontend additions must match the existing design system exactly (amber/teal/ink/coral palette, `font-display`/`font-sans`/`font-mono` roles, existing `Button`/`BookingCard`/`AppShell` components) — no new visual direction.

---

### Task 1: Shared `get_trip_rules` helper — extract from `chat.py` into `policy/rules.py`

**Files:**
- Modify: `api/policy/rules.py`
- Modify: `api/routes/chat.py`
- Modify: `api/tests/test_policy_rules.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `get_trip_rules(db, trip_id: str) -> tuple[str, dict]` (`api/policy/rules.py`) — returns `(policy_id, rules)`, raises `fastapi.HTTPException(404)` if the trip or its company's policy doesn't exist. Task 3 (`POST /trips/{trip_id}/bookings`) consumes this directly.

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `api/tests/test_policy_rules.py` (the file currently only imports `check_rules`; add `get_trip_rules` to that same import line, and add `MagicMock`/`pytest`/`HTTPException` imports at the top):

```python
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from policy.rules import check_rules, get_trip_rules
from travel.models import FlightOption, HotelOption
```

(This replaces the existing two-line import block at the top of the file — keep `RULES` and the four existing `test_*` functions exactly as they are, just append the following after them.)

```python
def _mock_db(trips_data, policies_data):
    db = MagicMock()

    def table(name):
        t = MagicMock()
        if name == "trips":
            t.select.return_value.eq.return_value.execute.return_value.data = trips_data
        elif name == "policies":
            t.select.return_value.eq.return_value.execute.return_value.data = policies_data
        return t

    db.table.side_effect = table
    return db


def test_get_trip_rules_returns_policy_id_and_rules():
    db = _mock_db(
        trips_data=[{"company_id": "company-1"}],
        policies_data=[{"id": "policy-1", "rules": RULES}],
    )

    policy_id, rules = get_trip_rules(db, "trip-1")

    assert policy_id == "policy-1"
    assert rules == RULES


def test_get_trip_rules_404s_when_trip_missing():
    db = _mock_db(trips_data=[], policies_data=[])

    with pytest.raises(HTTPException) as exc_info:
        get_trip_rules(db, "nope")

    assert exc_info.value.status_code == 404


def test_get_trip_rules_404s_when_policy_missing():
    db = _mock_db(trips_data=[{"company_id": "company-1"}], policies_data=[])

    with pytest.raises(HTTPException) as exc_info:
        get_trip_rules(db, "trip-1")

    assert exc_info.value.status_code == 404
```

- [ ] **Step 2: Verify it fails**

Run: `cd api && .venv/Scripts/python.exe -m pytest tests/test_policy_rules.py -v && cd ..`
Expected: FAIL — `ImportError: cannot import name 'get_trip_rules'`.

- [ ] **Step 3: Add `get_trip_rules` to `api/policy/rules.py`**

Add this import at the top of the file (it currently has no `fastapi` import):

```python
from fastapi import HTTPException
```

Append this function at the end of the file (after `check_rules`, do not modify `check_rules` or `RuleCheckResult`):

```python
def get_trip_rules(db, trip_id: str) -> tuple[str, dict]:
    """Trip -> company -> policy lookup, shared by the chat agent's context
    injection (routes/chat.py) and the guided wizard's booking endpoint
    (routes/bookings.py) -- one lookup, two front doors."""
    trips = db.table("trips").select("company_id").eq("id", trip_id).execute().data
    if not trips:
        raise HTTPException(status_code=404, detail="Trip not found")
    company_id = trips[0]["company_id"]

    policies = db.table("policies").select("id, rules").eq("company_id", company_id).execute().data
    if not policies:
        raise HTTPException(status_code=404, detail="Policy not found for company")
    return policies[0]["id"], policies[0]["rules"]
```

- [ ] **Step 4: Verify the new tests pass**

Run: `cd api && .venv/Scripts/python.exe -m pytest tests/test_policy_rules.py -v && cd ..`
Expected: PASS (7 tests: 4 existing + 3 new).

- [ ] **Step 5: Refactor `api/routes/chat.py` to use it**

The file currently starts:

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.graph import build_agent_graph
from core.db import get_db
```

Change the first import line (drop `HTTPException` — it's no longer used anywhere in this file after this refactor) and add the new import:

```python
from fastapi import APIRouter
from pydantic import BaseModel

from agent.graph import build_agent_graph
from core.db import get_db
from policy.rules import get_trip_rules
```

Then replace this block inside `handle_chat_message` (the trip/company/policy lookup):

```python
def handle_chat_message(db, trip_id: str, content: str) -> str:
    trips = db.table("trips").select("company_id").eq("id", trip_id).execute().data
    if not trips:
        raise HTTPException(status_code=404, detail="Trip not found")
    company_id = trips[0]["company_id"]

    policies = (
        db.table("policies").select("id, rules").eq("company_id", company_id).execute().data
    )
    if not policies:
        raise HTTPException(status_code=404, detail="Policy not found for company")
    policy_id = policies[0]["id"]
    rules = policies[0]["rules"]
```

with:

```python
def handle_chat_message(db, trip_id: str, content: str) -> str:
    policy_id, rules = get_trip_rules(db, trip_id)
```

Everything below that in `handle_chat_message` (the `db.table("trip_messages").insert(...)` line onward) stays exactly as it is — this is a pure extraction, not a behavior change.

- [ ] **Step 6: Verify the full suite still passes**

Run: `cd api && .venv/Scripts/python.exe -m pytest -v && .venv/Scripts/python.exe -m ruff check . && cd ..`
Expected: full suite passes, including `tests/test_routes_chat.py` unchanged (same mock call chain: `db.table("trips").select("company_id").eq(...)` then `db.table("policies").select("id, rules").eq(...)` — identical to before the refactor, just relocated). Ruff must show no unused-import warning for `HTTPException` in `chat.py`.

- [ ] **Step 7: Commit**

```bash
git add api/policy/rules.py api/routes/chat.py api/tests/test_policy_rules.py
git commit -m "refactor: extract trip->company->policy rules lookup into policy.rules.get_trip_rules"
```

---

### Task 2: `api/routes/trips.py` — create-trip endpoint + search passthrough

**Files:**
- Create: `api/routes/trips.py`
- Modify: `api/main.py`
- Create: `api/tests/test_routes_trips.py`

**Interfaces:**
- Consumes: `search_travel` (`api/agent/tools.py`, existing, unmodified).
- Produces: `POST /trips` (body `{"employee_id": str}`) → `{"id": str}`. `GET /trips/{trip_id}/search?kind=&origin_or_location=&destination=&date=` → `list[dict]`. Both importable as `from routes.trips import router`. Task 8 (frontend `/plan` chooser and `/plan/[tripId]` wizard) consumes both.

- [ ] **Step 1: Write the failing tests**

Create `api/tests/test_routes_trips.py`:

```python
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


@patch("routes.trips.get_db")
def test_create_trip_creates_row_and_returns_id(mock_get_db):
    db = MagicMock()
    employees_table = MagicMock()
    employees_table.select.return_value.eq.return_value.execute.return_value.data = [
        {"company_id": "company-1"}
    ]
    trips_table = MagicMock()
    trips_table.insert.return_value.execute.return_value.data = [{"id": "trip-1"}]

    def table(name):
        return {"employees": employees_table, "trips": trips_table}[name]

    db.table.side_effect = table
    mock_get_db.return_value = db

    response = client.post("/trips", json={"employee_id": "emp-1"})

    assert response.status_code == 200
    assert response.json() == {"id": "trip-1"}
    inserted = trips_table.insert.call_args[0][0]
    assert inserted["employee_id"] == "emp-1"
    assert inserted["company_id"] == "company-1"
    assert "thread_id" in inserted


@patch("routes.trips.get_db")
def test_create_trip_404s_when_employee_missing(mock_get_db):
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    mock_get_db.return_value = db

    response = client.post("/trips", json={"employee_id": "nope"})

    assert response.status_code == 404


@patch("routes.trips.search_travel")
def test_search_passes_query_params_through_to_search_travel(mock_search_travel):
    mock_search_travel.invoke.return_value = [{"id": "f1", "airline": "Skyward Air"}]

    response = client.get(
        "/trips/trip-1/search",
        params={
            "kind": "flight",
            "origin_or_location": "SFO",
            "destination": "JFK",
            "date": "2026-09-01",
        },
    )

    assert response.status_code == 200
    assert response.json() == [{"id": "f1", "airline": "Skyward Air"}]
    mock_search_travel.invoke.assert_called_once_with({
        "kind": "flight",
        "origin_or_location": "SFO",
        "destination": "JFK",
        "date": "2026-09-01",
    })
```

- [ ] **Step 2: Verify it fails**

Run: `cd api && .venv/Scripts/python.exe -m pytest tests/test_routes_trips.py -v && cd ..`
Expected: FAIL — 404 (routes don't exist / `ModuleNotFoundError` on the patch target).

- [ ] **Step 3: Write `api/routes/trips.py`**

```python
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.tools import search_travel
from core.db import get_db

router = APIRouter()


class TripIn(BaseModel):
    employee_id: str


@router.post("/trips")
def create_trip(body: TripIn) -> dict:
    db = get_db()
    employees = (
        db.table("employees").select("company_id").eq("id", body.employee_id).execute().data
    )
    if not employees:
        raise HTTPException(status_code=404, detail="Employee not found")

    trip = db.table("trips").insert({
        "company_id": employees[0]["company_id"],
        "employee_id": body.employee_id,
        "thread_id": str(uuid.uuid4()),
    }).execute().data[0]
    return {"id": trip["id"]}


@router.get("/trips/{trip_id}/search")
def search(
    trip_id: str,
    kind: str,
    origin_or_location: str,
    destination: str = "",
    date: str = "",
) -> list[dict]:
    return search_travel.invoke({
        "kind": kind,
        "origin_or_location": origin_or_location,
        "destination": destination,
        "date": date,
    })
```

(`trip_id` isn't used inside `search` — search doesn't depend on the trip — but keeps this route trip-scoped, matching every other route's shape.)

- [ ] **Step 4: Wire into `api/main.py`**

Add the import alongside the existing router imports:

```python
from routes.trips import router as trips_router
```

Add the include alongside the existing `app.include_router(...)` calls:

```python
app.include_router(trips_router)
```

- [ ] **Step 5: Verify tests pass**

Run: `cd api && .venv/Scripts/python.exe -m pytest -v && .venv/Scripts/python.exe -m ruff check . && cd ..`
Expected: full suite passes, including the 3 new tests.

- [ ] **Step 6: Commit**

```bash
git add api/routes/trips.py api/main.py api/tests/test_routes_trips.py
git commit -m "feat: add POST /trips and GET /trips/{trip_id}/search endpoints"
```

---

### Task 3: `POST /trips/{trip_id}/bookings` — direct booking endpoint

**Files:**
- Modify: `api/routes/bookings.py`
- Modify: `api/tests/test_routes_bookings.py`

**Interfaces:**
- Consumes: `get_trip_rules` (Task 1, `policy/rules.py`), `create_booking` (`api/agent/tools.py`, existing, unmodified).
- Produces: `POST /trips/{trip_id}/bookings` (body `{"kind": str, "details": dict}`) → `{"id": str, "status": "booked"|"pending_approval", "violations": list[str]}`. Task 8 (frontend wizard Review step) consumes this.

- [ ] **Step 1: Write the failing tests**

`api/tests/test_routes_bookings.py` already imports everything these tests need (`patch`, `httpx`, `TestClient`, `app`, `DuffelAPIError`) — no import changes required. Append these three tests at the end of the file:

```python
@patch("routes.bookings.create_booking")
@patch("routes.bookings.get_trip_rules")
@patch("routes.bookings.get_db")
def test_create_trip_booking_returns_booked_result(mock_get_db, mock_get_trip_rules, mock_create_booking):
    mock_get_trip_rules.return_value = ("policy-1", {"max_fare_class": "economy"})
    mock_create_booking.invoke.return_value = {"id": "booking-9", "status": "booked", "violations": []}

    response = client.post(
        "/trips/trip-1/bookings",
        json={"kind": "flight", "details": {"id": "f1", "price_cents": 30000}},
    )

    assert response.status_code == 200
    assert response.json() == {"id": "booking-9", "status": "booked", "violations": []}
    mock_create_booking.invoke.assert_called_once_with({
        "trip_id": "trip-1",
        "kind": "flight",
        "details": {"id": "f1", "price_cents": 30000},
        "rules": {"max_fare_class": "economy"},
    })


@patch("routes.bookings.create_booking")
@patch("routes.bookings.get_trip_rules")
@patch("routes.bookings.get_db")
def test_create_trip_booking_409s_when_fare_expired(mock_get_db, mock_get_trip_rules, mock_create_booking):
    mock_get_trip_rules.return_value = ("policy-1", {"max_fare_class": "economy"})
    mock_create_booking.invoke.side_effect = DuffelAPIError(
        code="offer_no_longer_available",
        message="Please select another offer.",
        status_code=422,
    )

    response = client.post(
        "/trips/trip-1/bookings",
        json={"kind": "flight", "details": {"id": "f1"}},
    )

    assert response.status_code == 409
    assert "Please select another offer." in response.json()["detail"]


@patch("routes.bookings.create_booking")
@patch("routes.bookings.get_trip_rules")
@patch("routes.bookings.get_db")
def test_create_trip_booking_504s_on_timeout(mock_get_db, mock_get_trip_rules, mock_create_booking):
    mock_get_trip_rules.return_value = ("policy-1", {"max_fare_class": "economy"})
    mock_create_booking.invoke.side_effect = httpx.TimeoutException("read timed out")

    response = client.post(
        "/trips/trip-1/bookings",
        json={"kind": "flight", "details": {"id": "f1"}},
    )

    assert response.status_code == 504
```

- [ ] **Step 2: Verify it fails**

Run: `cd api && .venv/Scripts/python.exe -m pytest tests/test_routes_bookings.py -v && cd ..`
Expected: FAIL — 404 (route doesn't exist yet).

- [ ] **Step 3: Add the route to `api/routes/bookings.py`**

The file currently starts:

```python
import httpx
from fastapi import APIRouter, HTTPException

from core.db import get_db
from travel.duffel_client import DuffelAPIError, UnknownOfferError
from travel.ticketing import issue_ticket

router = APIRouter()
```

Change it to add the two new imports and the `BookingIn` model:

```python
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.tools import create_booking
from core.db import get_db
from policy.rules import get_trip_rules
from travel.duffel_client import DuffelAPIError, UnknownOfferError
from travel.ticketing import issue_ticket

router = APIRouter()


class BookingIn(BaseModel):
    kind: str
    details: dict
```

Add this route (anywhere in the file after `router = APIRouter()`, e.g. right after the existing `list_bookings` function):

```python
@router.post("/trips/{trip_id}/bookings")
def create_trip_booking(trip_id: str, body: BookingIn) -> dict:
    db = get_db()
    _, rules = get_trip_rules(db, trip_id)

    try:
        return create_booking.invoke({
            "trip_id": trip_id,
            "kind": body.kind,
            "details": body.details,
            "rules": rules,
        })
    except (DuffelAPIError, UnknownOfferError) as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Could not ticket this booking: {getattr(exc, 'message', exc)} "
                "Search again for a current fare."
            ),
        ) from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail=(
                "The airline did not respond in time and no order was found. "
                "Check the Duffel dashboard before trying again."
            ),
        ) from exc
```

- [ ] **Step 4: Verify tests pass**

Run: `cd api && .venv/Scripts/python.exe -m pytest -v && .venv/Scripts/python.exe -m ruff check . && cd ..`
Expected: full suite passes, including the 3 new tests and all pre-existing `test_routes_bookings.py` tests (approve/reject) unchanged.

- [ ] **Step 5: Commit**

```bash
git add api/routes/bookings.py api/tests/test_routes_bookings.py
git commit -m "feat: add POST /trips/{trip_id}/bookings, wrapping create_booking directly"
```

---

### Task 4: `AppShell` header widened for a stepper + `Stepper` component

**Files:**
- Modify: `web/src/components/app-shell.tsx`
- Create: `web/src/components/plan/stepper.tsx`

**Interfaces:**
- Consumes: `cn` (`web/src/lib/utils.ts`, existing).
- Produces: `Stepper({ currentIndex }: { currentIndex: number })` (`web/src/components/plan/stepper.tsx`) — renders the fixed 4-stage "Trip basics / Flight / Hotel / Review" progress row. `AppShell`'s `title` prop widened from `string` to `React.ReactNode`. Task 8 (`/plan/[tripId]`) consumes both.

- [ ] **Step 1: Widen `AppShell`'s `title` prop**

In `web/src/components/app-shell.tsx`, change:

```tsx
export function AppShell({
  title,
  meta,
  actions,
  children,
}: {
  title?: string;
  meta?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
```

to:

```tsx
export function AppShell({
  title,
  meta,
  actions,
  children,
}: {
  title?: React.ReactNode;
  meta?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
```

No other change in this file — every existing caller (`home`, `itinerary`, `duty-of-care`, `chat`) already passes a plain string, which is still valid `React.ReactNode`.

- [ ] **Step 2: Write `web/src/components/plan/stepper.tsx`**

```tsx
import { cn } from "@/lib/utils";

const STEP_LABELS = ["Trip basics", "Flight", "Hotel", "Review"] as const;

export function Stepper({ currentIndex }: { currentIndex: number }) {
  return (
    <div className="flex items-center gap-3">
      {STEP_LABELS.map((label, i) => {
        const done = i < currentIndex;
        const active = i === currentIndex;
        return (
          <div key={label} className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <span
                aria-hidden
                className={cn(
                  "flex size-6 flex-none items-center justify-center rounded-full font-mono text-[11px] font-semibold",
                  done
                    ? "bg-[var(--color-teal)] text-white"
                    : active
                      ? "bg-[var(--color-ink)] text-white"
                      : "border border-[var(--color-line)] text-[var(--color-slate)]",
                )}
              >
                {done ? "✓" : i + 1}
              </span>
              <span
                className={cn(
                  "font-mono text-xs tracking-[0.06em] uppercase",
                  active
                    ? "font-semibold text-[var(--color-ink)]"
                    : "text-[var(--color-slate)]",
                )}
              >
                {label}
              </span>
            </div>
            {i < STEP_LABELS.length - 1 && (
              <span aria-hidden className="h-px w-6 bg-[var(--color-line)]" />
            )}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 3: Verify the frontend still type-checks**

Run: `cd web && npx tsc --noEmit -p tsconfig.json && cd ..`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add web/src/components/app-shell.tsx web/src/components/plan/stepper.tsx
git commit -m "feat: widen AppShell title to ReactNode, add Stepper component"
```

---

### Task 5: `OptionCard` component — selectable search result

**Files:**
- Create: `web/src/components/plan/option-card.tsx`

**Interfaces:**
- Consumes: `Button` (`web/src/components/ui/button.tsx`, existing), `cn` (`web/src/lib/utils.ts`).
- Produces: `SearchOption` type (`{ kind: "flight" } & FlightSearchResult | { kind: "hotel" } & HotelSearchResult`), `OptionCard({ option, selected, onSelect })` (`web/src/components/plan/option-card.tsx`). Task 8 (`/plan/[tripId]`) consumes both.

- [ ] **Step 1: Write `web/src/components/plan/option-card.tsx`**

```tsx
"use client";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type FlightSearchResult = {
  id: string;
  airline: string;
  fare_class: string;
  origin: string;
  destination: string;
  depart_date: string;
  price_cents: number;
};

export type HotelSearchResult = {
  id: string;
  name: string;
  location: string;
  check_in: string;
  check_out: string;
  nightly_rate_cents: number;
};

export type SearchOption =
  | ({ kind: "flight" } & FlightSearchResult)
  | ({ kind: "hotel" } & HotelSearchResult);

function money(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

export function OptionCard({
  option,
  selected,
  onSelect,
}: {
  option: SearchOption;
  selected: boolean;
  onSelect: () => void;
}) {
  const title = option.kind === "flight" ? option.airline : option.name;
  const subLabel = option.kind === "flight" ? option.fare_class : option.location;
  const route =
    option.kind === "flight"
      ? `${option.origin} → ${option.destination}`
      : `${option.check_in} – ${option.check_out}`;
  const price =
    option.kind === "flight"
      ? money(option.price_cents)
      : `${money(option.nightly_rate_cents)}/night`;

  return (
    <div
      className={cn(
        "flex items-center justify-between rounded-xl border bg-white p-4 transition-colors duration-[var(--duration-quick)]",
        selected
          ? "border-[1.5px] border-[var(--color-ink)]"
          : "border-[rgba(27,42,65,0.1)]",
      )}
    >
      <div>
        <div className="flex items-baseline gap-2">
          <span className="font-sans text-[15px] font-semibold text-[var(--color-ink)]">
            {title}
          </span>
          <span className="font-mono text-xs text-[var(--color-slate)] uppercase">
            {subLabel}
          </span>
        </div>
        <div className="mt-1 font-mono text-sm text-[var(--color-ink)]">{route}</div>
      </div>
      <div className="flex items-center gap-3">
        <span className="font-mono text-sm font-semibold text-[var(--color-ink)]">
          {price}
        </span>
        <Button
          type="button"
          variant={selected ? "confirm" : "secondary"}
          size="sm"
          onClick={onSelect}
        >
          {selected ? "Selected" : "Select"}
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify the frontend still type-checks**

Run: `cd web && npx tsc --noEmit -p tsconfig.json && cd ..`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/src/components/plan/option-card.tsx
git commit -m "feat: add OptionCard component for selecting flight/hotel search results"
```

---

### Task 6: `/plan` chooser page + "Plan a trip" entry points on Home and Trips

**Files:**
- Create: `web/src/app/plan/page.tsx`
- Modify: `web/src/app/home/page.tsx`
- Modify: `web/src/app/itinerary/page.tsx`

**Interfaces:**
- Consumes: `POST /trips` (Task 2), `supabaseBrowserClient` (existing).
- Produces: `/plan` route. No new exports other files import.

- [ ] **Step 1: Write `web/src/app/plan/page.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabaseBrowserClient } from "@/lib/supabase";
import { AppShell } from "@/components/app-shell";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export default function PlanChooserPage() {
  const router = useRouter();
  const [employeeId, setEmployeeId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState<"guided" | "chat" | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      const {
        data: { user },
      } = await supabaseBrowserClient.auth.getUser();
      if (!user) {
        setError("Sign in to plan a trip.");
        return;
      }
      const { data, error: err } = await supabaseBrowserClient
        .from("employees")
        .select("id")
        .eq("auth_user_id", user.id)
        .maybeSingle();
      if (!active) return;
      if (err) {
        setError(err.message);
        return;
      }
      if (data) setEmployeeId(data.id as string);
    })();
    return () => {
      active = false;
    };
  }, []);

  async function start(mode: "guided" | "chat") {
    if (!employeeId) return;
    setStarting(mode);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/trips`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ employee_id: employeeId }),
      });
      if (!res.ok) throw new Error(`Could not start a trip (${res.status})`);
      const { id } = (await res.json()) as { id: string };
      router.push(mode === "guided" ? `/plan/${id}` : `/chat/${id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
      setStarting(null);
    }
  }

  return (
    <AppShell title="Plan a trip" meta="Choose how you'd like to book">
      <div className="flex min-h-0 flex-1 items-center justify-center px-8">
        <div className="flex w-full max-w-[640px] flex-col gap-4">
          {error && (
            <p role="alert" className="font-sans text-sm text-[var(--color-coral)]">
              {error}
            </p>
          )}
          <div className="grid grid-cols-2 gap-5">
            <button
              type="button"
              disabled={!employeeId || starting !== null}
              onClick={() => start("guided")}
              className="flex flex-col items-start gap-2 rounded-2xl border border-[rgba(27,42,65,0.1)] bg-white p-6 text-left shadow-[0_1px_3px_rgba(27,42,65,0.08)] transition-[transform,box-shadow] duration-[var(--duration-quick)] hover:-translate-y-1 hover:shadow-[0_12px_28px_rgba(27,42,65,0.16)] focus-visible:ring-2 focus-visible:ring-[var(--color-teal)] focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50"
            >
              <span className="font-display text-lg font-semibold text-[var(--color-ink)]">
                Guided
              </span>
              <span className="font-sans text-sm text-[var(--color-slate)]">
                Step by step: trip basics, flight, hotel, then review and book.
              </span>
              <span className="mt-2 font-mono text-xs font-semibold text-[var(--color-amber-ink)]">
                {starting === "guided" ? "Starting…" : "Start guided →"}
              </span>
            </button>

            <button
              type="button"
              disabled={!employeeId || starting !== null}
              onClick={() => start("chat")}
              className="flex flex-col items-start gap-2 rounded-2xl border border-[rgba(27,42,65,0.1)] bg-white p-6 text-left shadow-[0_1px_3px_rgba(27,42,65,0.08)] transition-[transform,box-shadow] duration-[var(--duration-quick)] hover:-translate-y-1 hover:shadow-[0_12px_28px_rgba(27,42,65,0.16)] focus-visible:ring-2 focus-visible:ring-[var(--color-teal)] focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50"
            >
              <span className="font-display text-lg font-semibold text-[var(--color-ink)]">
                Chat
              </span>
              <span className="font-sans text-sm text-[var(--color-slate)]">
                Tell Wayfare where you need to be in plain English.
              </span>
              <span className="mt-2 font-mono text-xs font-semibold text-[var(--color-amber-ink)]">
                {starting === "chat" ? "Starting…" : "Start chat →"}
              </span>
            </button>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
```

- [ ] **Step 2: Add "Plan a trip" to Home's hero**

In `web/src/app/home/page.tsx`, replace this block:

```tsx
          <div className="absolute inset-x-8 top-5 flex items-center">
            <Link href="/itinerary">
              <span className="rounded-[10px] bg-[var(--color-amber)] px-[18px] py-2.5 font-sans text-sm font-semibold text-[var(--color-ink)] transition-[filter] duration-[var(--duration-quick)] hover:brightness-95">
                Review trips
              </span>
            </Link>
          </div>
```

with:

```tsx
          <div className="absolute inset-x-8 top-5 flex items-center gap-3">
            <Link href="/plan">
              <span className="rounded-[10px] bg-[var(--color-amber)] px-[18px] py-2.5 font-sans text-sm font-semibold text-[var(--color-ink)] transition-[filter] duration-[var(--duration-quick)] hover:brightness-95">
                Plan a trip
              </span>
            </Link>
            <Link href="/itinerary">
              <span className="rounded-[10px] bg-white/10 px-[18px] py-2.5 font-sans text-sm font-semibold text-white ring-1 ring-white/25 ring-inset transition-colors duration-[var(--duration-quick)] hover:bg-white/20">
                Review trips
              </span>
            </Link>
          </div>
```

- [ ] **Step 3: Add "Plan a trip" to the Trips page header**

In `web/src/app/itinerary/page.tsx`, add this import alongside the existing ones (right after `"use client";`):

```tsx
import Link from "next/link";
```

Then replace the `actions` prop on `<AppShell>`:

```tsx
      actions={
        <div className="flex gap-1 rounded-[9px] bg-[#f4f2ee] p-[3px]">
          {(Object.keys(FILTERS) as FilterKey[]).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setFilter(key)}
              aria-pressed={filter === key}
              className={cn(
                "rounded-[7px] px-3.5 py-1.5 font-sans text-[13px] transition-colors duration-[var(--duration-quick)] focus-visible:ring-2 focus-visible:ring-[var(--color-teal)] focus-visible:outline-none",
                filter === key
                  ? "bg-white font-semibold text-[var(--color-ink)] shadow-[0_1px_2px_rgba(27,42,65,0.08)]"
                  : "font-medium text-[var(--color-slate)] hover:text-[var(--color-ink)]",
              )}
            >
              {FILTERS[key].label}
              {key === "pending" && pendingCount > 0 && ` ${pendingCount}`}
            </button>
          ))}
        </div>
      }
```

with:

```tsx
      actions={
        <>
          <div className="flex gap-1 rounded-[9px] bg-[#f4f2ee] p-[3px]">
            {(Object.keys(FILTERS) as FilterKey[]).map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => setFilter(key)}
                aria-pressed={filter === key}
                className={cn(
                  "rounded-[7px] px-3.5 py-1.5 font-sans text-[13px] transition-colors duration-[var(--duration-quick)] focus-visible:ring-2 focus-visible:ring-[var(--color-teal)] focus-visible:outline-none",
                  filter === key
                    ? "bg-white font-semibold text-[var(--color-ink)] shadow-[0_1px_2px_rgba(27,42,65,0.08)]"
                    : "font-medium text-[var(--color-slate)] hover:text-[var(--color-ink)]",
                )}
              >
                {FILTERS[key].label}
                {key === "pending" && pendingCount > 0 && ` ${pendingCount}`}
              </button>
            ))}
          </div>
          <Link href="/plan">
            <Button type="button" size="sm">
              Plan a trip
            </Button>
          </Link>
        </>
      }
```

(`Button` is already imported in this file.)

- [ ] **Step 4: Verify the frontend still type-checks**

Run: `cd web && npx tsc --noEmit -p tsconfig.json && cd ..`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add web/src/app/plan/page.tsx web/src/app/home/page.tsx web/src/app/itinerary/page.tsx
git commit -m "feat: add /plan chooser page and Plan a trip entry points on Home and Trips"
```

---

### Task 7: `/plan/[tripId]` — the guided wizard

**Files:**
- Create: `web/src/app/plan/[tripId]/page.tsx`

**Interfaces:**
- Consumes: `AppShell` (Task 4, widened `title`), `Stepper` (Task 4), `OptionCard`/`SearchOption` (Task 5), `BookingCard`/`Booking` (`web/src/components/booking-card.tsx`, existing), `Button` (existing), `GET /trips/{trip_id}/search` (Task 2), `POST /trips/{trip_id}/bookings` (Task 3).
- Produces: `/plan/[tripId]` route. Nothing else depends on it.

- [ ] **Step 1: Write `web/src/app/plan/[tripId]/page.tsx`**

```tsx
"use client";

import { use, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { Stepper } from "@/components/plan/stepper";
import { OptionCard, type SearchOption } from "@/components/plan/option-card";
import { BookingCard, type Booking } from "@/components/booking-card";
import { Button } from "@/components/ui/button";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

const inputClass =
  "rounded-md border border-black/10 bg-white px-3 py-2 font-sans text-sm text-[var(--color-ink)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-amber)]";

type Basics = {
  origin: string;
  destination: string;
  departDate: string;
  returnDate: string;
};

type BookingResult = {
  id: string;
  status: "booked" | "pending_approval";
  violations: string[];
};

export default function PlanWizardPage({
  params,
}: {
  params: Promise<{ tripId: string }>;
}) {
  const { tripId } = use(params);

  const [step, setStep] = useState(0); // 0 basics, 1 flight, 2 hotel, 3 review
  const [basics, setBasics] = useState<Basics>({
    origin: "",
    destination: "",
    departDate: "",
    returnDate: "",
  });

  const [flightOptions, setFlightOptions] = useState<SearchOption[]>([]);
  const [selectedFlight, setSelectedFlight] = useState<SearchOption | null>(null);
  const [hotelOptions, setHotelOptions] = useState<SearchOption[]>([]);
  const [selectedHotel, setSelectedHotel] = useState<SearchOption | null>(null);

  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [booking, setBooking] = useState(false);
  const [flightResult, setFlightResult] = useState<BookingResult | null>(null);
  const [hotelResult, setHotelResult] = useState<BookingResult | null>(null);

  async function searchFlights() {
    setSearching(true);
    setError(null);
    try {
      const query = new URLSearchParams({
        kind: "flight",
        origin_or_location: basics.origin,
        destination: basics.destination,
        date: basics.departDate,
      });
      const res = await fetch(`${API_BASE}/trips/${tripId}/search?${query}`);
      if (!res.ok) throw new Error(`Search failed (${res.status})`);
      const data = (await res.json()) as Omit<SearchOption, "kind">[];
      setFlightOptions(data.map((o) => ({ ...o, kind: "flight" }) as SearchOption));
      setStep(1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setSearching(false);
    }
  }

  async function searchHotels() {
    setSearching(true);
    setError(null);
    try {
      const query = new URLSearchParams({
        kind: "hotel",
        origin_or_location: basics.destination,
        destination: basics.returnDate,
        date: basics.departDate,
      });
      const res = await fetch(`${API_BASE}/trips/${tripId}/search?${query}`);
      if (!res.ok) throw new Error(`Search failed (${res.status})`);
      const data = (await res.json()) as Omit<SearchOption, "kind">[];
      setHotelOptions(data.map((o) => ({ ...o, kind: "hotel" }) as SearchOption));
      setStep(2);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setSearching(false);
    }
  }

  async function bookOne(kind: "flight" | "hotel", details: SearchOption): Promise<BookingResult> {
    const res = await fetch(`${API_BASE}/trips/${tripId}/bookings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, details }),
    });
    if (!res.ok) throw new Error(`Booking failed (${res.status})`);
    return (await res.json()) as BookingResult;
  }

  async function confirmAndBook() {
    setBooking(true);
    setError(null);
    try {
      if (selectedFlight) setFlightResult(await bookOne("flight", selectedFlight));
      if (selectedHotel) setHotelResult(await bookOne("hotel", selectedHotel));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBooking(false);
    }
  }

  return (
    <AppShell
      title={<Stepper currentIndex={step} />}
      actions={
        <Link href={`/chat/${tripId}`}>
          <Button type="button" variant="secondary" size="sm">
            Switch to chat
          </Button>
        </Link>
      }
    >
      <div className="min-h-0 flex-1 overflow-y-auto px-8 py-8">
        {step === 0 && (
          <div className="mx-auto flex w-full max-w-[480px] flex-col gap-4">
            <h2 className="font-display text-lg font-semibold text-[var(--color-ink)]">
              Where and when?
            </h2>

            <label className="flex flex-col gap-1.5">
              <span className="font-mono text-xs tracking-wide text-[var(--color-slate)] uppercase">
                Origin (airport code)
              </span>
              <input
                value={basics.origin}
                onChange={(e) =>
                  setBasics({ ...basics, origin: e.target.value.toUpperCase() })
                }
                placeholder="SFO"
                className={inputClass}
              />
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="font-mono text-xs tracking-wide text-[var(--color-slate)] uppercase">
                Destination (airport code)
              </span>
              <input
                value={basics.destination}
                onChange={(e) =>
                  setBasics({ ...basics, destination: e.target.value.toUpperCase() })
                }
                placeholder="JFK"
                className={inputClass}
              />
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="font-mono text-xs tracking-wide text-[var(--color-slate)] uppercase">
                Depart date
              </span>
              <input
                type="date"
                value={basics.departDate}
                onChange={(e) => setBasics({ ...basics, departDate: e.target.value })}
                className={inputClass}
              />
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="font-mono text-xs tracking-wide text-[var(--color-slate)] uppercase">
                Return / check-out date
              </span>
              <input
                type="date"
                value={basics.returnDate}
                onChange={(e) => setBasics({ ...basics, returnDate: e.target.value })}
                className={inputClass}
              />
            </label>

            {error && (
              <p role="alert" className="font-sans text-sm text-[var(--color-coral)]">
                {error}
              </p>
            )}

            <Button
              type="button"
              disabled={
                searching ||
                !basics.origin ||
                !basics.destination ||
                !basics.departDate ||
                !basics.returnDate
              }
              onClick={searchFlights}
              className="self-start"
            >
              {searching ? "Searching…" : "Search flights →"}
            </Button>
          </div>
        )}

        {step === 1 && (
          <div className="mx-auto flex w-full max-w-[560px] flex-col gap-3">
            <h2 className="font-display text-lg font-semibold text-[var(--color-ink)]">
              Choose a flight
            </h2>
            {error && (
              <p role="alert" className="font-sans text-sm text-[var(--color-coral)]">
                {error}
              </p>
            )}
            {flightOptions.map((option) => (
              <OptionCard
                key={option.id}
                option={option}
                selected={selectedFlight?.id === option.id}
                onSelect={() => setSelectedFlight(option)}
              />
            ))}
            <div className="mt-2 flex gap-3">
              <Button type="button" variant="secondary" onClick={() => setStep(0)}>
                Back
              </Button>
              <Button
                type="button"
                disabled={!selectedFlight || searching}
                onClick={searchHotels}
              >
                {searching ? "Searching…" : "Next: Hotel →"}
              </Button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="mx-auto flex w-full max-w-[560px] flex-col gap-3">
            <h2 className="font-display text-lg font-semibold text-[var(--color-ink)]">
              Choose a hotel (optional)
            </h2>
            {error && (
              <p role="alert" className="font-sans text-sm text-[var(--color-coral)]">
                {error}
              </p>
            )}
            {hotelOptions.map((option) => (
              <OptionCard
                key={option.id}
                option={option}
                selected={selectedHotel?.id === option.id}
                onSelect={() => setSelectedHotel(option)}
              />
            ))}
            <div className="mt-2 flex gap-3">
              <Button type="button" variant="secondary" onClick={() => setStep(1)}>
                Back
              </Button>
              <Button
                type="button"
                variant="quiet"
                onClick={() => {
                  setSelectedHotel(null);
                  setStep(3);
                }}
              >
                Skip hotel
              </Button>
              <Button type="button" disabled={!selectedHotel} onClick={() => setStep(3)}>
                Next: Review →
              </Button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="mx-auto flex w-full max-w-[560px] flex-col gap-4">
            <h2 className="font-display text-lg font-semibold text-[var(--color-ink)]">
              Review
            </h2>

            {selectedFlight && (
              <BookingCard
                booking={{ ...selectedFlight, status: flightResult?.status } as Booking}
              />
            )}
            {selectedHotel && (
              <BookingCard
                booking={{ ...selectedHotel, status: hotelResult?.status } as Booking}
              />
            )}

            {error && (
              <p role="alert" className="font-sans text-sm text-[var(--color-coral)]">
                {error}
              </p>
            )}
            {flightResult && (
              <p className="font-sans text-sm text-[var(--color-ink)]">
                Flight{" "}
                {flightResult.status === "booked" ? "booked." : "needs manager approval."}
                {flightResult.violations.length > 0 &&
                  ` (${flightResult.violations.join(", ")})`}
              </p>
            )}
            {hotelResult && (
              <p className="font-sans text-sm text-[var(--color-ink)]">
                Hotel{" "}
                {hotelResult.status === "booked" ? "booked." : "needs manager approval."}
                {hotelResult.violations.length > 0 &&
                  ` (${hotelResult.violations.join(", ")})`}
              </p>
            )}

            <div className="mt-2 flex items-center gap-3">
              <Button
                type="button"
                variant="secondary"
                onClick={() => setStep(2)}
                disabled={booking}
              >
                Back
              </Button>
              <Button
                type="button"
                disabled={booking || !selectedFlight || !!flightResult}
                onClick={confirmAndBook}
              >
                {booking ? "Booking…" : flightResult ? "Booked" : "Confirm and book"}
              </Button>
              {flightResult && (
                <Link href={`/chat/${tripId}`}>
                  <Button type="button" variant="ghost">
                    Go to chat →
                  </Button>
                </Link>
              )}
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
```

- [ ] **Step 2: Verify the frontend still type-checks**

Run: `cd web && npx tsc --noEmit -p tsconfig.json && cd ..`
Expected: no errors.

- [ ] **Step 3: Verify the frontend builds**

Run: `npm run build --prefix web`
Expected: build succeeds (confirms the new dynamic route compiles).

- [ ] **Step 4: Commit**

```bash
git add web/src/app/plan/\[tripId\]/page.tsx
git commit -m "feat: add /plan/[tripId] guided booking wizard"
```

---

### Task 8: "Switch to guided" button on the chat page

**Files:**
- Modify: `web/src/app/chat/[tripId]/page.tsx`

**Interfaces:**
- Consumes: `Button` (existing), `Link` (Next.js, existing dependency).
- Produces: nothing further tasks depend on — this closes the loop, making the switch symmetric.

- [ ] **Step 1: Add the imports**

In `web/src/app/chat/[tripId]/page.tsx`, change:

```tsx
"use client";

import { use, useCallback, useEffect, useState } from "react";
import { supabaseBrowserClient } from "@/lib/supabase";
import { MessageList, type Message } from "@/components/chat/message-list";
import { MessageInput } from "@/components/chat/message-input";
import { AppShell } from "@/components/app-shell";
```

to:

```tsx
"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { supabaseBrowserClient } from "@/lib/supabase";
import { MessageList, type Message } from "@/components/chat/message-list";
import { MessageInput } from "@/components/chat/message-input";
import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
```

- [ ] **Step 2: Add the switch button**

Change:

```tsx
    <AppShell title="Plan a trip" meta={`TRIP ${tripId.slice(0, 8)}`}>
```

to:

```tsx
    <AppShell
      title="Plan a trip"
      meta={`TRIP ${tripId.slice(0, 8)}`}
      actions={
        <Link href={`/plan/${tripId}`}>
          <Button type="button" variant="secondary" size="sm">
            Switch to guided
          </Button>
        </Link>
      }
    >
```

- [ ] **Step 3: Verify the frontend still type-checks**

Run: `cd web && npx tsc --noEmit -p tsconfig.json && cd ..`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add web/src/app/chat/\[tripId\]/page.tsx
git commit -m "feat: add Switch to guided button on the chat page"
```

---

### Task 9: End-to-end verification

**Files:** none (verification only).

- [ ] **Step 1: Full backend suite**

Run: `cd api && .venv/Scripts/python.exe -m pytest -v && .venv/Scripts/python.exe -m ruff check . && cd ..`
Expected: full suite passes (all prior tests plus this plan's ~9 new tests), ruff clean.

- [ ] **Step 2: Full frontend check**

Run: `cd web && npx tsc --noEmit -p tsconfig.json && npm run build --prefix web && cd ..`
Expected: no type errors, build succeeds.

- [ ] **Step 3: Manual browser check — guided golden path**

With both servers running (`cd api && .venv/Scripts/python.exe -m uvicorn main:app --reload --port 8001` and `npm run dev --prefix web`) and signed in as the seeded demo user: from `/home`, click **Plan a trip** → **Guided**. Fill in trip basics (e.g. `SFO` → `JFK`, any future dates), search flights, pick one, search hotels, pick one (or Skip hotel), Review, **Confirm and book**. Confirm both items show a real `booked`/`pending_approval` status, and the new bookings appear on `/itinerary`.

- [ ] **Step 4: Manual browser check — mode switching**

From the wizard's Review screen, click **Switch to chat** — confirm the same trip's (empty, or freshly booked) chat thread loads. From chat, click **Switch to guided** — confirm the wizard reloads at step 1 (Trip basics) for the same trip (this is the known, spec-flagged gap: no resumption — confirm it behaves as documented, not that it crashes).

- [ ] **Step 5: Manual browser check — chat golden path via the new entry point**

From `/itinerary`, click **Plan a trip** → **Chat**. Confirm a new trip is created and its empty chat thread loads. Send a message and confirm the agent responds (requires `ANTHROPIC_API_KEY` configured).

- [ ] **Step 6: Update the spec's status**

Add a short note at the end of `docs/superpowers/specs/2026-07-29-guided-booking-wizard-design.md` (a new `## Status` section) recording: implemented and manually verified on `<date>`; the two deferred items (step-resumption, agent-visible wizard bookings) remain open, not addressed by this plan.

```bash
git add docs/superpowers/specs/2026-07-29-guided-booking-wizard-design.md
git commit -m "docs: mark guided booking wizard spec as implemented"
```

---

## After all tasks land

An employee can start a brand-new trip from the UI for the first time (previously impossible), choose guided or chat, complete a booking through the guided wizard entirely via deterministic endpoints reusing the existing tool layer, and switch between both modes freely for the same trip. Explicitly still open, per the spec: smart step-resumption when switching modes mid-trip, and giving the chat agent visibility into bookings the wizard already made.
