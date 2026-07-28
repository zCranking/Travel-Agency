# Phase 2 + Code-Buildable Phase 3/4 Slices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the single booking agent into three specialized LangGraph nodes (booking/policy/disruption) behind a cheap intent router, add a duty-of-care view, a local eval harness, optional LangSmith tracing, a versioned API-key-gated external agent endpoint (the Phase 3 licensing seam), and a mocked expense-sync adapter (the Phase 4 integration seam) — all on top of the already-shipped, live-tested Phase 1 MVP.

**Architecture:** No new services. Everything lands inside the existing `api/` (FastAPI + LangGraph) and `web/` (Next.js) trees, following the exact patterns Phase 1 established: mock-first external integrations behind a swappable interface, deterministic pytest-covered logic, plain LangGraph tool functions (still no MCP — three specialist nodes is still not enough surface to justify the protocol layer).

**Tech Stack:** Same as Phase 1 (Python 3.13/FastAPI/LangGraph/Supabase/Next.js), plus `python-dotenv` (loads `.env` into real `os.environ` so LangSmith's SDK, which reads env vars directly rather than through our `Settings` object, picks up tracing config without bespoke plumbing).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-28-phase2-multiagent-design.md` — implements it in full. Explicitly out of scope: SOC2 (any type), Spotnana migration, real licensing deals, client acquisition, Temporal/cron background jobs, self-hosted Langfuse.
- No MCP tool-wiring layer — same deviation as Phase 1, still holds.
- `api/` remains the only place that calls Claude, Duffel, Voyage, or (now) LangSmith/expense APIs — `web/` never talks to them directly.
- `build_agent_graph()` keeps its exact external interface (`.invoke({"messages": [...]})` in, `result["messages"][-1].content` out) — `routes/chat.py` must NOT need to change for the multi-agent refactor.
- Every task must leave the repo in a state where `git status` is clean after its own commit.
- The duty-of-care UI task MUST invoke the `frontend-design` skill (or, for a subagent without that tool, follow `docs/superpowers/specs/2026-07-27-foundation-mvp-design.md`'s existing token system exactly — same navy/amber/teal/coral palette, Space Grotesk/Plex Sans/Plex Mono, boarding-pass motif) — do not leave it at generic defaults.
- Mocked destination risk levels in the duty-of-care view must be visibly labeled as placeholder data, never presented as real risk intelligence.

---

### Task 1: Disruption mock + `check_disruptions` tool

**Files:**
- Modify: `api/travel/models.py`
- Modify: `api/travel/duffel_client.py`
- Modify: `api/agent/tools.py`
- Create: `api/tests/test_disruptions.py`

**Interfaces:**
- Consumes: `get_db()` (`api/core/db.py`).
- Produces: `Disruption` model (`api/travel/models.py`: `type: str`, `message: str`). `MockDuffelClient.get_disruption(details: dict) -> Disruption | None` (`api/travel/duffel_client.py`). `check_disruptions` LangChain tool (`api/agent/tools.py`), signature `check_disruptions(trip_id: str) -> list[dict]`. Task 2 (multi-agent graph) binds this tool into the new disruption specialist node.

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_disruptions.py`:

```python
from unittest.mock import patch

from agent.tools import check_disruptions
from travel.duffel_client import MockDuffelClient


def test_get_disruption_flags_pacific_crest_flights():
    client = MockDuffelClient()
    details = {"airline": "Pacific Crest", "origin": "SFO", "destination": "JFK"}
    disruption = client.get_disruption(details)
    assert disruption is not None
    assert disruption.type == "delay"
    assert "delayed" in disruption.message.lower()


def test_get_disruption_none_for_other_airlines():
    client = MockDuffelClient()
    details = {"airline": "Skyward Air", "origin": "SFO", "destination": "JFK"}
    assert client.get_disruption(details) is None


def test_get_disruption_none_for_hotels():
    client = MockDuffelClient()
    details = {"name": "Harborview Inn", "location": "NYC"}
    assert client.get_disruption(details) is None


@patch("agent.tools.get_db")
def test_check_disruptions_reports_only_affected_bookings(mock_get_db):
    mock_get_db.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "b1", "kind": "flight", "details": {"airline": "Pacific Crest", "origin": "SFO", "destination": "JFK"}},
        {"id": "b2", "kind": "flight", "details": {"airline": "Skyward Air", "origin": "SFO", "destination": "JFK"}},
        {"id": "b3", "kind": "hotel", "details": {"name": "Harborview Inn", "location": "NYC"}},
    ]

    result = check_disruptions.invoke({"trip_id": "trip-1"})

    assert len(result) == 1
    assert result[0]["booking_id"] == "b1"
    assert result[0]["type"] == "delay"
```

- [ ] **Step 2: Verify it fails**

Run: `cd api && .venv/Scripts/python.exe -m pytest tests/test_disruptions.py -v && cd ..`
Expected: FAIL — `ImportError: cannot import name 'check_disruptions'`.

- [ ] **Step 3: Add `Disruption` to `api/travel/models.py`**

Append to the existing file (do not touch `FlightOption`/`HotelOption`/`BookingConfirmation`):

```python
class Disruption(BaseModel):
    type: str  # "delay" | "cancellation"
    message: str
```

- [ ] **Step 4: Add `get_disruption` to `api/travel/duffel_client.py`**

Add this import at the top (alongside the existing `travel.models` import, extend it):

```python
from travel.models import BookingConfirmation, Disruption, FlightOption, HotelOption
```

Add this method to `MockDuffelClient` (any position in the class body):

```python
    def get_disruption(self, details: dict) -> Disruption | None:
        """Mocked, deterministic: Pacific Crest flights are always shown as
        disrupted, everything else is clean. No real disruption feed exists
        yet — this proves the check_disruptions/rebooking path end to end
        against a stable fixture instead of random data."""
        if details.get("airline") == "Pacific Crest":
            return Disruption(
                type="delay",
                message="Pacific Crest flight delayed 3 hours due to crew scheduling.",
            )
        return None
```

- [ ] **Step 5: Add `check_disruptions` to `api/agent/tools.py`**

Add this tool function (any position after the existing imports/tools):

```python
@tool
def check_disruptions(trip_id: str) -> list[dict]:
    """Check a trip's flight bookings for disruptions (delays/cancellations).
    Returns only the bookings that are actually affected."""
    db = get_db()
    bookings = (
        db.table("bookings").select("id, kind, details").eq("trip_id", trip_id).execute().data
    )
    disruptions = []
    for booking in bookings:
        if booking["kind"] != "flight":
            continue
        disruption = _duffel.get_disruption(booking["details"])
        if disruption is not None:
            disruptions.append(
                {"booking_id": booking["id"], "type": disruption.type, "message": disruption.message}
            )
    return disruptions
```

- [ ] **Step 6: Verify tests pass**

Run: `cd api && .venv/Scripts/python.exe -m pytest -v && cd ..`
Expected: full suite passes (this task's 4 new tests plus all prior tests).

- [ ] **Step 7: Commit**

```bash
git add api/travel/models.py api/travel/duffel_client.py api/agent/tools.py api/tests/test_disruptions.py
git commit -m "feat: add mocked disruption detection and check_disruptions tool"
```

---

### Task 2: Multi-agent graph — supervisor + booking/policy/disruption nodes

**Files:**
- Modify: `api/agent/graph.py` (full rewrite of its body — same public interface)
- Create: `api/tests/test_agent_routing.py`

**Interfaces:**
- Consumes: `search_travel`, `check_policy`, `why_out_of_policy`, `create_booking` (Phase 1, `api/agent/tools.py`), `check_disruptions` (Task 1).
- Produces: `build_agent_graph()` — SAME external signature as before (returns a compiled graph; `.invoke({"messages": [...]})` in, last message's `.content` out). `classify_intent(text: str) -> str` (returns `"booking"`, `"policy"`, or `"disruption"`), importable as `from agent.graph import classify_intent, build_agent_graph` — Task 5 (eval harness) may reference `classify_intent` directly for assertions.

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_agent_routing.py`:

```python
from agent.graph import classify_intent


def test_classify_intent_routes_disruption_keywords():
    assert classify_intent("Is my flight delayed?") == "disruption"
    assert classify_intent("Was my trip cancelled?") == "disruption"
    assert classify_intent("Can you rebook me on a different flight?") == "disruption"


def test_classify_intent_routes_policy_keywords():
    assert classify_intent("Why is business class not allowed?") == "policy"
    assert classify_intent("Is this hotel compliant with our policy?") == "policy"


def test_classify_intent_defaults_to_booking():
    assert classify_intent("Find me a flight from SFO to JFK on 2026-09-01") == "booking"
    assert classify_intent("Book the economy option") == "booking"
```

- [ ] **Step 2: Verify it fails**

Run: `cd api && .venv/Scripts/python.exe -m pytest tests/test_agent_routing.py -v && cd ..`
Expected: FAIL — `ImportError: cannot import name 'classify_intent'`.

- [ ] **Step 3: Rewrite `api/agent/graph.py`**

Replace the entire file:

```python
from typing import Annotated

from langchain_anthropic import ChatAnthropic
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from typing_extensions import TypedDict

from agent.tools import (
    check_disruptions,
    check_policy,
    create_booking,
    search_travel,
    why_out_of_policy,
)
from core.config import settings

BOOKING_TOOLS = [search_travel, check_policy, create_booking]
POLICY_TOOLS = [check_policy, why_out_of_policy]
DISRUPTION_TOOLS = [check_disruptions]

BOOKING_PROMPT = (
    "You are Wayfare's booking specialist. Search flights/hotels, always "
    "check_policy before booking, and call create_booking only after the "
    "employee confirms a choice."
)
POLICY_PROMPT = (
    "You are Wayfare's policy specialist. Answer 'is this in policy' and "
    "'why' questions thoroughly, citing the policy document via "
    "why_out_of_policy whenever you can. You do not book anything."
)
DISRUPTION_PROMPT = (
    "You are Wayfare's disruption specialist. Use check_disruptions to look "
    "up whether a trip's flights are delayed or cancelled, and explain "
    "clearly what changed. You do not book anything new."
)

_DISRUPTION_KEYWORDS = ("disrupt", "delay", "delayed", "cancel", "rebook", "flight status")
_POLICY_KEYWORDS = ("why", "policy", "compliant", "allowed", "in-policy", "in policy", "out of policy")


def classify_intent(text: str) -> str:
    """Cheap keyword routing — no extra LLM call needed to pick a
    specialist. Order matters: disruption keywords are checked before
    policy keywords since 'rebook' could otherwise look booking-flavored."""
    lowered = text.lower()
    if any(k in lowered for k in _DISRUPTION_KEYWORDS):
        return "disruption"
    if any(k in lowered for k in _POLICY_KEYWORDS):
        return "policy"
    return "booking"


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


def _last_human_text(state: AgentState) -> str:
    for message in reversed(state["messages"]):
        role = getattr(message, "type", None) or (
            message.get("role") if isinstance(message, dict) else None
        )
        if role in ("human", "user"):
            content = getattr(message, "content", None) or (
                message.get("content") if isinstance(message, dict) else ""
            )
            return content if isinstance(content, str) else ""
    return ""


def _route(state: AgentState) -> AgentState:
    return state


def _route_edge(state: AgentState) -> str:
    return classify_intent(_last_human_text(state))


def _make_specialist(tools: list, system_prompt: str):
    model = ChatAnthropic(model="claude-sonnet-5", api_key=settings.anthropic_api_key).bind_tools(tools)

    def call_model(state: AgentState) -> AgentState:
        messages = [{"role": "system", "content": system_prompt}, *state["messages"]]
        return {"messages": [model.invoke(messages)]}

    return call_model


def build_agent_graph():
    graph = StateGraph(AgentState)

    graph.add_node("route", _route)
    graph.set_entry_point("route")

    specialists = {
        "booking": (BOOKING_TOOLS, BOOKING_PROMPT),
        "policy": (POLICY_TOOLS, POLICY_PROMPT),
        "disruption": (DISRUPTION_TOOLS, DISRUPTION_PROMPT),
    }

    routes = {}
    for name, (tools, prompt) in specialists.items():
        agent_node = f"{name}_agent"
        tools_node = f"{name}_tools"
        graph.add_node(agent_node, _make_specialist(tools, prompt))
        graph.add_node(tools_node, ToolNode(tools))
        graph.add_conditional_edges(agent_node, tools_condition, {"tools": tools_node, END: END})
        graph.add_edge(tools_node, agent_node)
        routes[name] = agent_node

    graph.add_conditional_edges("route", _route_edge, routes)
    return graph.compile()
```

- [ ] **Step 4: Verify tests pass**

Run: `cd api && .venv/Scripts/python.exe -m pytest -v && cd ..`
Expected: full suite passes. Pay attention to `tests/test_agent_tools.py` and any test importing `agent.graph` — they must still pass unchanged, confirming the external interface didn't break.

- [ ] **Step 5: Verify lint passes**

Run: `cd api && .venv/Scripts/python.exe -m ruff check . && cd ..`

- [ ] **Step 6: Commit**

```bash
git add api/agent/graph.py api/tests/test_agent_routing.py
git commit -m "feat: split single agent into booking/policy/disruption specialist nodes"
```

---

### Task 3: Duty-of-care backend endpoint

**Files:**
- Create: `api/routes/duty_of_care.py`
- Modify: `api/main.py`
- Create: `api/tests/test_routes_duty_of_care.py`

**Interfaces:**
- Consumes: `get_db()` (`api/core/db.py`).
- Produces: `GET /duty-of-care` — importable as `from routes.duty_of_care import router`. Returns `list[dict]`, one entry per employee: `{"employee_id": str, "name": str, "trip": {"trip_id": str, "destination": str, "risk_level": "low"|"medium"|"high", "bookings": [...]} | None}`. Task 4 (frontend) consumes this shape directly.

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_routes_duty_of_care.py`:

```python
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


@patch("routes.duty_of_care.get_db")
def test_duty_of_care_returns_employee_with_trip_and_risk(mock_get_db):
    db = MagicMock()

    def table(name):
        t = MagicMock()
        if name == "employees":
            t.select.return_value.execute.return_value.data = [
                {"id": "emp-1", "name": "Jordan Lee"}
            ]
        elif name == "trips":
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
                {"id": "trip-1", "thread_id": "trip-1"}
            ]
        elif name == "bookings":
            t.select.return_value.eq.return_value.execute.return_value.data = [
                {
                    "id": "b1",
                    "kind": "flight",
                    "details": {"destination": "JFK"},
                    "status": "booked",
                }
            ]
        return t

    db.table.side_effect = table
    mock_get_db.return_value = db

    response = client.get("/duty-of-care")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["employee_id"] == "emp-1"
    assert body[0]["name"] == "Jordan Lee"
    assert body[0]["trip"]["trip_id"] == "trip-1"
    assert body[0]["trip"]["destination"] == "JFK"
    assert body[0]["trip"]["risk_level"] in ("low", "medium", "high")
    assert len(body[0]["trip"]["bookings"]) == 1


@patch("routes.duty_of_care.get_db")
def test_duty_of_care_employee_with_no_trip(mock_get_db):
    db = MagicMock()

    def table(name):
        t = MagicMock()
        if name == "employees":
            t.select.return_value.execute.return_value.data = [
                {"id": "emp-2", "name": "Priya Nair"}
            ]
        elif name == "trips":
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        return t

    db.table.side_effect = table
    mock_get_db.return_value = db

    response = client.get("/duty-of-care")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["trip"] is None
```

- [ ] **Step 2: Verify it fails**

Run: `cd api && .venv/Scripts/python.exe -m pytest tests/test_routes_duty_of_care.py -v && cd ..`
Expected: FAIL — 404 (route doesn't exist).

- [ ] **Step 3: Write `api/routes/duty_of_care.py`**

```python
from fastapi import APIRouter

from core.db import get_db

router = APIRouter()

_RISK_LEVELS = ["low", "medium", "high"]


def _mock_risk_level(destination: str) -> str:
    """Placeholder risk data -- deterministic from the destination string,
    NOT a real risk feed (no Riskline/equivalent integration exists yet).
    The frontend must label this as placeholder, never real intelligence."""
    return _RISK_LEVELS[hash(destination) % len(_RISK_LEVELS)]


@router.get("/duty-of-care")
def duty_of_care() -> list[dict]:
    db = get_db()
    employees = db.table("employees").select("id, name").execute().data

    result = []
    for employee in employees:
        trips = (
            db.table("trips")
            .select("id, thread_id")
            .eq("employee_id", employee["id"])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
            .data
        )
        if not trips:
            result.append({"employee_id": employee["id"], "name": employee["name"], "trip": None})
            continue

        trip = trips[0]
        bookings = (
            db.table("bookings").select("id, kind, details, status").eq("trip_id", trip["id"]).execute().data
        )
        destination = next(
            (b["details"].get("destination") for b in bookings if b["kind"] == "flight"),
            "Unknown",
        )
        result.append(
            {
                "employee_id": employee["id"],
                "name": employee["name"],
                "trip": {
                    "trip_id": trip["id"],
                    "destination": destination,
                    "risk_level": _mock_risk_level(destination),
                    "bookings": bookings,
                },
            }
        )
    return result
```

- [ ] **Step 4: Wire into `api/main.py`**

Modify `api/main.py` — add the import alongside the existing two router imports:

```python
from routes.duty_of_care import router as duty_of_care_router
```

And add the include alongside the existing two `app.include_router(...)` calls:

```python
app.include_router(duty_of_care_router)
```

- [ ] **Step 5: Verify tests pass**

Run: `cd api && .venv/Scripts/python.exe -m pytest -v && cd ..`

- [ ] **Step 6: Commit**

```bash
git add api/routes/duty_of_care.py api/main.py api/tests/test_routes_duty_of_care.py
git commit -m "feat: add duty-of-care backend endpoint aggregating employees/trips/risk"
```

---

### Task 4: Duty-of-care frontend page

**Files:**
- Create: `web/src/app/duty-of-care/page.tsx`

**Interfaces:**
- Consumes: `GET /duty-of-care` (Task 3), same response shape.
- Produces: nothing further tasks depend on.

- [ ] **Step 1: Follow the existing design system**

No new visual direction needed — reuse the exact tokens/patterns from `web/src/app/itinerary/page.tsx` (same header bar treatment: `bg-[var(--color-ink)]`, `font-display` wordmark, `font-mono` page label) and `design-direction.md`'s color vars. The one new element is the risk badge — render it as a small pill using `--color-teal` (low), `--color-amber` (medium), `--color-coral` (high), always paired with its text label (`Low risk`/`Medium risk`/`High risk`), never color alone, plus a `(placeholder data)` caption in `--color-slate` so nobody mistakes the mock for a real risk feed.

- [ ] **Step 2: Write `web/src/app/duty-of-care/page.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

type RiskLevel = "low" | "medium" | "high";

type DutyOfCareRow = {
  employee_id: string;
  name: string;
  trip: {
    trip_id: string;
    destination: string;
    risk_level: RiskLevel;
    bookings: { id: string; kind: "flight" | "hotel"; status: string }[];
  } | null;
};

const RISK_STYLES: Record<RiskLevel, string> = {
  low: "bg-[var(--color-teal)]",
  medium: "bg-[var(--color-amber)]",
  high: "bg-[var(--color-coral)]",
};

const RISK_LABELS: Record<RiskLevel, string> = {
  low: "Low risk",
  medium: "Medium risk",
  high: "High risk",
};

export default function DutyOfCarePage() {
  const [rows, setRows] = useState<DutyOfCareRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/duty-of-care`);
        if (!res.ok) throw new Error(`Failed to load (${res.status})`);
        const data = (await res.json()) as DutyOfCareRow[];
        if (active) setRows(data);
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : "Something went wrong.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-[640px] flex-col bg-white">
      <header className="flex items-baseline justify-between bg-[var(--color-ink)] px-4 py-3 text-white">
        <span className="font-display text-lg font-bold tracking-tight">Wayfare</span>
        <span className="font-mono text-xs text-white/60">Duty of Care</span>
      </header>

      <main className="flex flex-1 flex-col gap-3 p-4">
        {error && (
          <p role="alert" className="font-sans text-sm text-[var(--color-coral)]">
            {error}
          </p>
        )}

        {!loading && !error && rows.length === 0 && (
          <p className="font-sans text-sm text-[var(--color-slate)]">No employees found.</p>
        )}

        {rows.map((row) => (
          <div
            key={row.employee_id}
            className="flex items-center justify-between rounded-lg border border-black/5 bg-white p-4 shadow-[0_1px_3px_rgba(27,42,65,0.08)]"
          >
            <div>
              <p className="font-sans text-sm font-semibold text-[var(--color-ink)]">{row.name}</p>
              {row.trip ? (
                <p className="font-mono text-xs text-[var(--color-slate)]">{row.trip.destination}</p>
              ) : (
                <p className="font-mono text-xs text-[var(--color-slate)]">No active trip</p>
              )}
            </div>

            {row.trip && (
              <div className="flex flex-col items-end gap-0.5">
                <span
                  className={`rounded-full px-2.5 py-0.5 font-sans text-xs font-semibold text-white ${RISK_STYLES[row.trip.risk_level]}`}
                >
                  {RISK_LABELS[row.trip.risk_level]}
                </span>
                <span className="font-mono text-[10px] text-[var(--color-slate)]">
                  (placeholder data)
                </span>
              </div>
            )}
          </div>
        ))}
      </main>
    </div>
  );
}
```

- [ ] **Step 3: Verify build and lint pass**

Run: `npm run build --prefix web && npm run lint --prefix web`

- [ ] **Step 4: Manual browser check**

With both servers running and real credentials configured, open `/duty-of-care` and confirm: every seeded employee appears, the one with the live-tested trip shows its destination and a risk badge with the "(placeholder data)" caption, employees with no trip show "No active trip".

- [ ] **Step 5: Commit**

```bash
git add web/src/app/duty-of-care/
git commit -m "feat: add duty-of-care dashboard page"
```

---

### Task 5: Eval harness

**Files:**
- Create: `api/evals/__init__.py`
- Create: `api/evals/scenarios.py`
- Create: `api/evals/run.py`

**Interfaces:**
- Consumes: `build_agent_graph()` (`api/agent/graph.py`), `get_db()` (`api/core/db.py`).
- Produces: `SCENARIOS: list[dict]` (`api/evals/scenarios.py`) and a runnable `api/evals/run.py` script. Nothing else in the codebase depends on these — this is a standalone operator tool, not imported by application code.

- [ ] **Step 1: Write `api/evals/__init__.py`** (empty file)

- [ ] **Step 2: Write `api/evals/scenarios.py`**

```python
"""Hand-written eval scenarios. Each checks an OBSERVABLE OUTCOME (reply
text keywords, or the routed intent) rather than an exact tool-call
sequence -- exact sequences are too brittle against normal LLM
non-determinism to be a useful regression signal.
"""

SCENARIOS = [
    {
        "name": "book_economy_flight_in_policy",
        "message": "Find me a flight from SFO to JFK on 2026-09-01, then book the cheapest economy option.",
        "expect_reply_contains": ["booked", "econom"],
    },
    {
        "name": "book_business_flight_needs_approval",
        "message": "Book me on the Pacific Crest business class flight from SFO to JFK on 2026-09-01.",
        "expect_reply_contains": ["pending", "approv"],
    },
    {
        "name": "hotel_within_cap",
        "message": "Find hotels in New York for 2026-09-01 to 2026-09-03 and book the cheapest one.",
        "expect_reply_contains": ["booked"],
    },
    {
        "name": "policy_why_question",
        "message": "Why can't I book a business class flight?",
        "expect_intent": "policy",
    },
    {
        "name": "policy_compliance_question",
        "message": "Is a $200/night hotel compliant with our travel policy?",
        "expect_intent": "policy",
    },
    {
        "name": "disruption_status_question",
        "message": "Is my flight delayed?",
        "expect_intent": "disruption",
    },
    {
        "name": "disruption_rebook_question",
        "message": "Can you rebook me, I think my flight got cancelled?",
        "expect_intent": "disruption",
    },
    {
        "name": "booking_search_question",
        "message": "What flights are available from SFO to JFK on 2026-09-01?",
        "expect_intent": "booking",
    },
    {
        "name": "booking_default_ambiguous",
        "message": "I need to get to Chicago next week for a client meeting.",
        "expect_intent": "booking",
    },
    {
        "name": "policy_fare_class_wording",
        "message": "What's our max allowed fare class?",
        "expect_intent": "policy",
    },
    {
        "name": "disruption_delay_wording",
        "message": "Has anything changed with my upcoming flight?",
        "expect_reply_contains": [],  # weak assertion: just must not error, delay wording varies
    },
    {
        "name": "booking_hotel_search",
        "message": "I need a hotel in New York for two nights starting September 1st, 2026.",
        "expect_intent": "booking",
    },
    {
        "name": "policy_advance_booking_question",
        "message": "Why does our policy require booking 3 days in advance?",
        "expect_intent": "policy",
    },
    {
        "name": "booking_multi_city_ambiguous",
        "message": "Book me a flight to Denver for the 12th.",
        "expect_intent": "booking",
    },
    {
        "name": "disruption_status_check_specific",
        "message": "Can you check the status of my Pacific Crest flight for delays?",
        "expect_intent": "disruption",
    },
]
```

- [ ] **Step 3: Write `api/evals/run.py`**

```python
"""Manual eval runner -- not a pytest suite (these are live LLM calls with
real cost, not something to run on every commit). Usage:
    cd api && .venv/Scripts/python.exe evals/run.py
Requires ANTHROPIC_API_KEY; prints SKIPPED and exits 0 without one.
"""
import sys

from agent.graph import build_agent_graph, classify_intent
from core.config import settings
from evals.scenarios import SCENARIOS


def run() -> int:
    if not settings.anthropic_api_key:
        print("SKIPPED: no ANTHROPIC_API_KEY configured.")
        return 0

    graph = build_agent_graph()
    passed = 0
    failed = 0

    for scenario in SCENARIOS:
        name = scenario["name"]
        message = scenario["message"]
        ok = True
        reasons = []

        if "expect_intent" in scenario:
            actual_intent = classify_intent(message)
            if actual_intent != scenario["expect_intent"]:
                ok = False
                reasons.append(f"intent: expected {scenario['expect_intent']!r}, got {actual_intent!r}")

        if "expect_reply_contains" in scenario and scenario["expect_reply_contains"]:
            result = graph.invoke({"messages": [{"role": "user", "content": message}]})
            reply = result["messages"][-1].content
            reply_text = reply if isinstance(reply, str) else str(reply)
            missing = [kw for kw in scenario["expect_reply_contains"] if kw.lower() not in reply_text.lower()]
            if missing:
                ok = False
                reasons.append(f"reply missing keywords: {missing} (got: {reply_text[:200]!r})")

        if ok:
            passed += 1
            print(f"PASS  {name}")
        else:
            failed += 1
            print(f"FAIL  {name} -- {'; '.join(reasons)}")

    print(f"\n{passed}/{len(SCENARIOS)} passed, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
```

- [ ] **Step 4: Verify it skips cleanly without a key**

Run: `cd api && ANTHROPIC_API_KEY= .venv/Scripts/python.exe evals/run.py && cd ..`
Expected: prints `SKIPPED: no ANTHROPIC_API_KEY configured.`, exits 0. (On Windows/Git Bash, prefix works as shown; if the shell doesn't support inline env override, temporarily comment out the key in `api/.env` instead, run, then restore it.)

- [ ] **Step 5: Verify ruff passes**

Run: `cd api && .venv/Scripts/python.exe -m ruff check . && cd ..`

- [ ] **Step 6: Commit**

```bash
git add api/evals/
git commit -m "feat: add local eval harness with 15 hand-written scenarios"
```

---

### Task 6: LangSmith tracing (optional, env-driven)

**Files:**
- Modify: `api/pyproject.toml`
- Modify: `api/main.py`
- Modify: `api/.env.example`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing other tasks depend on — purely operational (tracing shows up in LangSmith's dashboard when configured, otherwise silently off).

- [ ] **Step 1: Add `python-dotenv` to `api/pyproject.toml`**

In the `dependencies` list, add (alongside the existing `fastapi`, `uvicorn[standard]`, etc. entries):

```toml
    "python-dotenv>=1.0",
```

- [ ] **Step 2: Install it**

Run: `cd api && .venv/Scripts/python.exe -m pip install -e ".[dev]" && cd ..`

- [ ] **Step 3: Load `.env` into real `os.environ` at process startup**

Modify `api/main.py` — add these two lines as the very first lines of the file, before any other import:

```python
from dotenv import load_dotenv

load_dotenv()

```

(Everything else in the file — the `FastAPI`/`CORSMiddleware`/router imports and below — stays exactly as it is today, just pushed two lines down.)

- [ ] **Step 4: Document the new optional env vars**

Modify `api/.env.example` — add these three lines at the end:

```
LANGSMITH_TRACING=false
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=wayfare-ai
```

- [ ] **Step 5: Verify the app still boots and tests still pass**

Run: `cd api && .venv/Scripts/python.exe -m pytest -v && .venv/Scripts/python.exe -m ruff check . && cd ..`
Expected: full suite passes unchanged — `load_dotenv()` is a no-op safety-wise, it only populates `os.environ` from `.env` if present.

- [ ] **Step 6: Note the manual follow-up (not part of this task)**

Actually seeing traces requires a real LangSmith account/API key, which isn't available in this environment. Once obtained: set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY=...` in `api/.env`, restart the backend, and traces appear automatically at smith.langchain.com — `langchain-anthropic`/`langgraph` pick up `LANGSMITH_*` env vars with zero further code changes. Record this as an open item, not something to fake-verify here.

- [ ] **Step 7: Commit**

```bash
git add api/pyproject.toml api/main.py api/.env.example
git commit -m "feat: load .env via python-dotenv, enabling optional LangSmith tracing"
```

---

### Task 7: External agent API boundary (Phase 3 licensing seam)

**Files:**
- Create: `supabase/migrations/00000000000003_licensees.sql`
- Create: `api/core/licensee_auth.py`
- Modify: `api/routes/chat.py` (extract shared logic, add nothing else)
- Create: `api/routes/v1_agent.py`
- Modify: `api/main.py`
- Modify: `api/scripts/seed.py`
- Create: `api/tests/test_v1_agent.py`

**Interfaces:**
- Consumes: `get_db()` (`api/core/db.py`).
- Produces: `licensees(id, name, api_key, created_at)` table. `require_licensee` FastAPI dependency (`api/core/licensee_auth.py`), signature `require_licensee(x_api_key: str = Header(...)) -> dict` (raises `HTTPException(401)` if the key doesn't match a row, else returns the licensee row). `POST /v1/agent/message` (body `{"trip_id": str, "content": str}`, header `X-API-Key`), returns `{"reply": str}` — same shape as the existing internal `POST /trips/{trip_id}/messages`. `handle_chat_message(db, trip_id: str, content: str) -> str` extracted from `routes/chat.py`, used by both the internal and `/v1` routes.

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_v1_agent.py`:

```python
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


@patch("routes.v1_agent.get_db")
def test_v1_agent_message_requires_valid_api_key(mock_get_db):
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    mock_get_db.return_value = db

    response = client.post(
        "/v1/agent/message",
        json={"trip_id": "trip-1", "content": "hi"},
        headers={"X-API-Key": "not-a-real-key"},
    )

    assert response.status_code == 401


@patch("routes.v1_agent.handle_chat_message")
@patch("routes.v1_agent.get_db")
def test_v1_agent_message_success_with_valid_key(mock_get_db, mock_handle):
    db = MagicMock()

    def table(name):
        t = MagicMock()
        if name == "licensees":
            t.select.return_value.eq.return_value.execute.return_value.data = [
                {"id": "lic-1", "name": "Wayfare Web"}
            ]
        return t

    db.table.side_effect = table
    mock_get_db.return_value = db
    mock_handle.return_value = "hello from the agent"

    response = client.post(
        "/v1/agent/message",
        json={"trip_id": "trip-1", "content": "hi"},
        headers={"X-API-Key": "real-key"},
    )

    assert response.status_code == 200
    assert response.json() == {"reply": "hello from the agent"}
    mock_handle.assert_called_once_with(db, "trip-1", "hi")
```

- [ ] **Step 2: Verify it fails**

Run: `cd api && .venv/Scripts/python.exe -m pytest tests/test_v1_agent.py -v && cd ..`
Expected: FAIL — 404 (route doesn't exist).

- [ ] **Step 3: Write the migration**

Create `supabase/migrations/00000000000003_licensees.sql`:

```sql
create table licensees (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    api_key text not null unique,
    created_at timestamptz not null default now()
);

alter table licensees enable row level security;
```

- [ ] **Step 4: Write `api/core/licensee_auth.py`**

```python
from fastapi import Header, HTTPException

from core.db import get_db


def require_licensee(x_api_key: str = Header(...)) -> dict:
    db = get_db()
    rows = db.table("licensees").select("id, name").eq("api_key", x_api_key).execute().data
    if not rows:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return rows[0]
```

- [ ] **Step 5: Extract shared logic in `api/routes/chat.py`**

The current file has a single route, `post_message`, that does everything
inline. Replace just the `post_message` function (keep `extract_reply_text`,
the imports, `router = APIRouter()`, `_graph = build_agent_graph()`, and the
`MessageIn` class exactly as they are) with these two functions:

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

    db.table("trip_messages").insert(
        {"trip_id": trip_id, "role": "user", "content": content}
    ).execute()

    # History includes the just-inserted user message (last), so we don't append it again.
    history = (
        db.table("trip_messages")
        .select("role, content")
        .eq("trip_id", trip_id)
        .order("created_at")
        .execute()
        .data
    )

    context = (
        f"Context for tool calls: trip_id={trip_id}, rules={rules}, policy_id={policy_id}. "
        "Always pass these exact values when calling check_policy, why_out_of_policy, "
        "or create_booking."
    )
    messages = [
        {"role": "system", "content": context},
        *[{"role": m["role"], "content": m["content"]} for m in history],
    ]

    result = _graph.invoke({"messages": messages})
    reply = extract_reply_text(result["messages"][-1].content)

    db.table("trip_messages").insert(
        {"trip_id": trip_id, "role": "assistant", "content": reply}
    ).execute()

    return reply


@router.post("/trips/{trip_id}/messages")
def post_message(trip_id: str, message: MessageIn) -> dict:
    db = get_db()
    reply = handle_chat_message(db, trip_id, message.content)
    return {"reply": reply}
```

This is a pure extraction — `handle_chat_message` is the old `post_message`
body verbatim (taking `db` as a parameter instead of calling `get_db()`
internally, and returning the plain string instead of a dict); `post_message`
now just fetches `db` and delegates. `test_routes_chat.py`'s existing tests
(which patch `routes.chat.get_db` and `routes.chat._graph`) must still pass
unchanged since the observable behavior of `POST /trips/{trip_id}/messages`
is identical.

- [ ] **Step 6: Write `api/routes/v1_agent.py`**

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.db import get_db
from core.licensee_auth import require_licensee
from routes.chat import handle_chat_message

router = APIRouter(prefix="/v1")


class AgentMessageIn(BaseModel):
    trip_id: str
    content: str


@router.post("/agent/message")
def v1_agent_message(body: AgentMessageIn, licensee: dict = Depends(require_licensee)) -> dict:
    db = get_db()
    reply = handle_chat_message(db, body.trip_id, body.content)
    return {"reply": reply}
```

- [ ] **Step 7: Wire into `api/main.py`**

Add the import alongside the existing router imports:

```python
from routes.v1_agent import router as v1_agent_router
```

Add the include alongside the existing `app.include_router(...)` calls:

```python
app.include_router(v1_agent_router)
```

- [ ] **Step 8: Seed a licensee row**

`api/scripts/seed.py` already has a module-level `import uuid` (used for the
trip's `thread_id`) — reuse it, don't add a new import. In `seed()`, insert
this block right after the existing `db.table("policies").insert({...}).execute()`
call and before the `# Jordan Lee is the demo login user` comment:

```python
    db.table("licensees").delete().eq("name", "Wayfare Web (internal)").execute()
    licensee = db.table("licensees").insert({
        "name": "Wayfare Web (internal)",
        "api_key": f"wf_live_{uuid.uuid4().hex}",
    }).execute().data[0]

```

Then change the second existing `print(...)` call (the one printing
`Demo login: ...`) from:

```python
    print(
        f"Demo login: {DEMO_LOGIN_EMAIL} / {DEMO_LOGIN_PASSWORD}  ->  trip id: {trip['id']}"
    )
```

to:

```python
    print(
        f"Demo login: {DEMO_LOGIN_EMAIL} / {DEMO_LOGIN_PASSWORD}  ->  trip id: {trip['id']}"
    )
    print(f"Licensee API key: {licensee['api_key']}")
```

- [ ] **Step 9: Verify tests pass**

Run: `cd api && .venv/Scripts/python.exe -m pytest -v && .venv/Scripts/python.exe -m ruff check . && cd ..`
Expected: full suite passes, including the two new `test_v1_agent.py` tests and the existing `test_routes_chat.py` tests (which must still pass against the refactored `handle_chat_message` extraction).

- [ ] **Step 10: Apply the migration and re-seed (manual follow-up, not required for the automated tests to pass, but needed before this is live-testable)**

If a Supabase project is already linked and its credentials are in `api/.env`: apply the new migration to it (via `npx supabase db push` if a local Supabase CLI link exists, or by hand through whatever tool was used for the prior two migrations), then re-run `cd api && .venv/Scripts/python.exe scripts/seed.py` to create the licensee row and print its key.

- [ ] **Step 11: Commit**

```bash
git add supabase/migrations/00000000000003_licensees.sql api/core/licensee_auth.py api/routes/chat.py api/routes/v1_agent.py api/main.py api/scripts/seed.py api/tests/test_v1_agent.py
git commit -m "feat: add versioned, API-key-gated external agent endpoint (licensing seam)"
```

---

### Task 8: Expense-platform sync adapter (Phase 4 integration seam)

**Files:**
- Create: `api/expense/__init__.py`
- Create: `api/expense/sync_client.py`
- Modify: `api/agent/tools.py`
- Create: `api/tests/test_expense_sync.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `SyncResult` model (`api/expense/sync_client.py`: `synced: bool`, `external_id: str | None`). `MockExpenseSyncClient.sync_booking(booking: dict) -> SyncResult`. Wired into `create_booking` (`api/agent/tools.py`) as a best-effort call after a `booked` (not `pending_approval`) row lands — nothing else depends on this.

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_expense_sync.py`:

```python
from expense.sync_client import MockExpenseSyncClient


def test_sync_booking_returns_success_with_external_id():
    client = MockExpenseSyncClient()
    result = client.sync_booking({"id": "b1", "kind": "flight", "price_cents": 28000})
    assert result.synced is True
    assert result.external_id is not None
    assert result.external_id.startswith("EXP-")
```

- [ ] **Step 2: Verify it fails**

Run: `cd api && .venv/Scripts/python.exe -m pytest tests/test_expense_sync.py -v && cd ..`
Expected: FAIL — `ModuleNotFoundError: No module named 'expense'`.

- [ ] **Step 3: Write `api/expense/__init__.py`** (empty file)

- [ ] **Step 4: Write `api/expense/sync_client.py`**

```python
"""Expense-platform sync (Ramp/Brex/Concur). MockExpenseSyncClient today; a
RealExpenseSyncClient implementing the same sync_booking method is a
drop-in swap once a real expense-platform API key exists.
"""
import uuid

from pydantic import BaseModel


class SyncResult(BaseModel):
    synced: bool
    external_id: str | None


class MockExpenseSyncClient:
    def sync_booking(self, booking: dict) -> SyncResult:
        return SyncResult(synced=True, external_id=f"EXP-{uuid.uuid4().hex[:8].upper()}")
```

- [ ] **Step 5: Wire into `create_booking` in `api/agent/tools.py`**

Add this import at the top, alongside the existing imports:

```python
from expense.sync_client import MockExpenseSyncClient
```

Add this module-level instance, alongside the existing `_duffel = MockDuffelClient()` line:

```python
_expense = MockExpenseSyncClient()
```

In `create_booking`, after the `row = db.table("bookings").insert(...).execute().data[0]` line and before the final `return` statement, add:

```python
    if status == "booked":
        try:
            _expense.sync_booking(row)
        except Exception:
            pass  # best-effort: sync failure must never block a completed booking
```

- [ ] **Step 6: Verify tests pass**

Run: `cd api && .venv/Scripts/python.exe -m pytest -v && cd ..`
Expected: full suite passes, including `test_agent_tools.py`'s existing `create_booking` tests (which don't mock `expense.sync_client`, so confirm the real `MockExpenseSyncClient` call doesn't raise or slow things down — it's synchronous and instant, no network I/O).

- [ ] **Step 7: Verify lint passes**

Run: `cd api && .venv/Scripts/python.exe -m ruff check . && cd ..`

- [ ] **Step 8: Commit**

```bash
git add api/expense/ api/agent/tools.py api/tests/test_expense_sync.py
git commit -m "feat: add mocked expense-platform sync adapter, wired into create_booking"
```

---

## After all tasks land

Update `docs/superpowers/specs/2026-07-28-phase2-multiagent-design.md` (or a session-log note) recording: Phase 2 core (multi-agent split, duty-of-care, eval harness) and the Phase 3/4 code slices (licensee API boundary, expense sync adapter) built and unit-tested; LangSmith tracing wired but unverified (no real key available); the licensees migration applied to the live Supabase project and re-seeded (Task 7 Step 10) as a manual follow-up if not done inline. Explicitly still open and NOT addressed by this plan: SOC2 (any type), Spotnana evaluation/migration, real licensing deals, client acquisition, entity formation, seller-of-travel state registration, E&O insurance, host-agency accreditation agreement — these remain the human founder's work, not further code.
