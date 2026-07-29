# Constraint Planner — Design

> Supersedes `docs/superpowers/specs/2026-07-29-guided-booking-wizard-design.md`.
> Builds on the foundation MVP, the phase-2 multi-agent split, and the live
> Duffel integration (`docs/superpowers/plans/2026-07-28-duffel-integration.md`).

## The problem this fixes

Today the agent is a natural-language front end over three tool calls:
`search_travel`, `check_policy`, `create_booking`. Every one of them takes
structured arguments and returns a structured result. The LLM's whole job is
parsing a sentence into those arguments and narrating the result back.

A form does that better. It is faster, cheaper, deterministic, and never
invents an offer id. The guided-booking-wizard spec proved the point by
accident: it reimplemented the entire booking flow with no model in the loop
and lost nothing. If a wizard can replace the agent, the agent was decoration.

The test that decides where a model belongs: **is there a single correct
query?** If yes, build a form. Search flights SFO→ORD on the 14th has one
correct answer, and a dropdown gets there faster than a paragraph.

Business travel does not pass that test. The real input is *"I have to be in
Chicago Tuesday at 2pm and Denver Thursday morning, I have a board call
Wednesday at 10 I can't miss, and I'd rather not red-eye."* That is
under-specified (which flights? how many nights? which airports?),
over-constrained (the cheap Denver flight departs during the board call), and
requires trading conflicting objectives against each other (cheapest violates
policy; the one that satisfies every preference costs 3x). There is no single
correct query. There is a feasible set and a judgment call.

**That** is the load-bearing job, and it is the one this spec builds.

## Architecture: interpret → solve → judge

Three stages, with a strict division of labour:

```
messy input ──► INTERPRET (AI) ──► TripIntent ──► SOLVE (code) ──► feasible set ──► JUDGE (AI) ──► ranked plans
                     │                  ▲              │                                 │
                     └── user confirms ─┘              └── empty? ──► binding constraint ─┘
```

**The invariant, stated once and enforced everywhere below: the AI never emits
an itinerary that code has not validated, and code never guesses at intent.**

This is the same lesson the Duffel work paid for. The agent hallucinated an
offer id and dropped its passenger ids, and the fix was not a better prompt —
it was refusing to act on the model's copy of anything the system already knew
authoritatively. Generalised: a model may *propose* and *explain*; only code
may *decide what is possible*.

Where the AI is deliberately absent:

- It does not search flights, price them, or pick dates. The solver does.
- It does not evaluate policy or compute totals. `check_rules` does.
- It does not book. `issue_ticket()` does, unchanged.

Where the AI is load-bearing, and no form substitutes:

- Turning prose or a pasted email into structured constraints.
- Choosing among feasible plans that trade cost, comfort, risk and policy
  against each other, and *saying why* in terms of the traveler's own stated
  constraints.
- Explaining infeasibility as a decision the traveler can act on ("move the
  Denver meeting to 11am, or accept a 6am departure") instead of an empty list.
- Synthesising scattered mechanical risk factors into one duty-of-care call.

## Data model

### New table: `meetings`

```sql
create table meetings (
    id uuid primary key default gen_random_uuid(),
    trip_id uuid not null references trips(id) on delete cascade,
    title text not null,
    city text,                 -- IATA code; required for in-person
    mode text not null check (mode in ('in_person', 'virtual')),
    starts_at timestamptz not null,
    ends_at timestamptz not null,
    -- false => binding. The solver may not violate a binding meeting, and an
    -- itinerary that would is infeasible, not merely worse.
    flexible boolean not null default false,
    created_at timestamptz not null default now(),
    check (mode = 'virtual' or city is not null),
    check (ends_at > starts_at)
);
```

`flexible` is one concept covering both modes: for an in-person meeting it
means presence may be waived (attend remotely); for a virtual one it means the
call may be taken from the air or missed. Default `false` — a meeting is
binding unless the traveler says otherwise. Fail closed, same as everywhere
else in this codebase.

Times are `timestamptz`. A meeting at 2pm in Chicago and a flight landing at
11:40am in Denver only compare correctly as instants.

### New table: `itineraries`

```sql
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
```

Itineraries are persisted rather than held client-side for the same reason
offers are cached server-side: selection must reference something the server
issued. A client — or a model — handing back an itinerary object gets the
`UnknownOfferError` treatment.

### Column additions

- `trips.origin_city text` — where the traveler starts and returns to.
- `trips.budget_cents int` — trip-level T&E budget. Soft, not hard: over
  budget is a flagged plan, not a hidden one.
- `employees.travel_preferences jsonb` — `{avoid_red_eyes, earliest_departure,
  latest_arrival, max_connections}`. All soft.

### `FlightOption` gains times

`FlightOption` today carries `depart_date` and no clock. A solver cannot
reason about a date. Added, with defaults so existing mock paths and tests
keep working:

```python
depart_at: str = ""   # ISO 8601 with UTC offset
arrive_at: str = ""
stops: int = 0
```

`RealDuffelClient.search_flights` fills these from
`slices[].segments[].departing_at`/`arriving_at` plus the airport's IANA
`time_zone`, resolved through `zoneinfo`. Duffel reports segment times as
naive local strings; attaching the airport's zone is what makes them
comparable. `MockDuffelClient` returns plausible times too, so the planner
demos and tests end to end with no Duffel token.

## The solver

`api/planning/solver.py`, a pure function with the search dependency injected:

```python
def solve(intent: TripIntent, search: SearchFn) -> PlanResult
```

`search` is `(origin, destination, date) -> list[FlightOption]`. Injecting it
is what makes the solver table-testable against fixtures with no network and
no monkeypatching of module globals.

1. **Derive the city sequence.** origin → the cities of binding in-person
   meetings in chronological order, consecutive duplicates collapsed → origin.
2. **Derive presence windows.** For each city, the traveler must be on the
   ground by `first_meeting.starts_at - GROUND_BUFFER` and may leave no
   earlier than `last_meeting.ends_at + GROUND_BUFFER`.
3. **Enumerate candidate legs.** For each hop, search the deadline date and
   the day before (an early meeting is usually reached by flying the night
   before).
4. **Filter each hop** by the hard checkers that apply to a single leg.
5. **Combine**, pruning as it goes: a combination survives only if each leg
   departs after the previous leg's arrival plus a connection buffer, and
   every presence window holds.
6. **Rank by total price and cap** at `_MAX_ITINERARIES = 5`. The judge reasons
   over a handful, not a combinatorial explosion.
7. **Evaluate soft checkers** on the survivors, attaching violations.
8. **If the feasible set is empty, find the binding constraint** by relaxing
   one hard constraint at a time and re-running. The first relaxation that
   yields a non-empty set names the constraint that is actually blocking. With
   two or three meetings this is cheap, and it is exactly the answer the
   traveler needs.
9. **Return** `PlanResult(itineraries=[...])` or
   `PlanResult(binding_constraint=Violation(...), relaxation=...)`.

Constants in one block: `GROUND_BUFFER = 90min` (airport to meeting),
`AIRPORT_LEAD = 120min` (arrive before departure), `CONNECTION_BUFFER = 60min`.
Domestic figures; international will need its own.

### Pluggable checkers

```python
HARD_CHECKERS = [check_presence, check_no_fly]
SOFT_CHECKERS = [check_red_eye, check_connections, check_budget, check_policy]
# each: (itinerary, intent) -> list[Violation]
```

This list is the international seam. `check_visa` and `check_passport_validity`
append to `HARD_CHECKERS` and nothing else in the solver changes — same
signature, same infeasibility machinery, same binding-constraint search. Not
built now; the shape is what keeps it from being a rewrite.

`check_policy` calls the existing `check_rules` per leg. Policy is soft here
on purpose: an out-of-policy plan is shown, flagged, and routed to approval —
the manager approval path already exists and works. Hiding it would make the
planner less useful than the chat it replaces.

### Plans ride on schedules, not offers

Duffel offers on aggregator content go stale in *seconds*, not the 20–30
minutes the docs imply — measured, during the live Duffel testing. So a plan
holds the schedule (carrier, times, route), which is stable, and treats price
as late-bound and indicative. Offer ids are carried opportunistically and
expected to be dead by selection time. **This makes reprice-at-selection
mandatory, not a nicety.**

## The AI layers

### Interpret — `api/planning/interpret.py`

```python
def interpret(text: str, today: date) -> TripIntentDraft
```

Free text or a pasted email → a **draft** `TripIntent` via structured output.
Never authoritative: the draft populates the meeting form and the traveler
confirms before anything is solved.

This is the crux of the "not shoved in" constraint. Making someone type
structured data as prose so a model can parse it back is the antipattern —
that is a form with extra latency and a failure mode. So the form is the
primary path, and interpretation is an accelerant for input that arrives
messy, which meeting invitations invariably do.

Validation rejects rather than guesses. Unparseable dates, cities that resolve
to no airport, `ends_at <= starts_at` — each comes back in an `unresolved`
list for the traveler to fill in. A guessed city books a real ticket to the
wrong place.

### Judge — `api/planning/judge.py`

```python
def judge(itineraries: list[Itinerary], intent: TripIntent) -> list[Ranking]
```

Input: the feasible set, the intent, the traveler's preferences, and the
code-computed soft violations **as facts**. Output:
`[{itinerary_id, rank, rationale, concerns[]}]`.

It does not recompute totals or re-evaluate policy; those arrive as inputs.
Every `itinerary_id` it returns must exist in the input set — validated, one
retry on mismatch, then a deterministic fallback to price order with a
generated rationale. The endpoint never fails because a model misbehaved, and
it never surfaces an id the solver did not produce.

### Risk — `api/planning/risk.py`

```python
def risk_factors(itinerary, intent) -> list[RiskFactor]   # deterministic
def synthesize(factors, itinerary) -> RiskAssessment      # AI
```

Code extracts the factors: arrival hour, ground transfer duration, connection
slack, early start, overnight gap, red-eye, back-to-back same-day city
changes. The model turns them into a severity and a concrete recommendation —
*"you land 11:40pm with a 7am cross-town start; take the airport hotel, not
downtown."* The factors render next to the advisory, so the assessment is
auditable rather than a black box, and a wrong severity is visibly wrong.

No factors means severity `low` and no model call. Paying a model to say
nothing is wrong is the kind of thing this spec exists to avoid.

This replaces `_mock_risk_level()` in `routes/duty_of_care.py`, which hashes
the destination string. That function is honest about being a placeholder; it
is also the single least defensible "AI feature" in the app.

## Endpoints — `api/routes/planning.py`

- `POST /trips` — create a trip. Lifted from the superseded wizard spec
  because it is still true that the UI has no way to start a trip.
- `POST /trips/{id}/meetings`, `GET`, `DELETE /meetings/{id}` — the form path.
- `POST /trips/{id}/interpret` — `{text}` → draft intent. Persists nothing.
- `POST /trips/{id}/plan` — solve, judge, assess risk, persist, return ranked.
  On infeasibility returns the binding constraint and suggested relaxations.
- `POST /itineraries/{id}/select` — reprice, then book.

### Reprice at selection

Re-search each leg and match it to the stored schedule by carrier and
departure time.

- Unchanged or cheaper → book straight through, leg by leg, through
  `issue_ticket()`.
- **Any** price increase, or a leg that no longer exists → return
  `{status: "reprice_required", itinerary: <updated>}` and wait for
  confirmation. Not a percentage threshold: silently charging more than the
  displayed price is not a thing to tune, and a decrease needs no consent.

Booking goes through `issue_ticket()` unchanged, so every protection the
Duffel work established — the offer cache, `UnknownOfferError`, the live-token
guard, ticket-before-insert — carries over untouched.

## Testing

The solver carries the weight, because it is where correctness lives and it is
a pure function over fixtures:

- Table-driven feasibility: given these meetings and these flights, exactly
  these itineraries are feasible.
- A landing 20 minutes before a meeting is rejected; three hours is accepted.
- A binding virtual meeting blocks an otherwise-valid flight; `flexible=true`
  relaxes it.
- Meetings in different timezones; a DST boundary.
- Infeasible cases name the correct binding constraint.
- Connection buffer and ground buffer boundaries.

AI layers get narrower tests: structured output validates against the schema,
interpretation returns `unresolved` instead of inventing a city, and — the
important one — **judge never references an itinerary id that was not in its
input**, with the fallback path asserted.

Planner scenarios join the existing `api/evals/` harness. The existing 62
tests must keep passing; nothing here changes the chat path.

## Scope

**In:** the migration; `api/planning/` (models, solver, checkers, interpret,
judge, risk); the endpoints above; reprice-at-selection; `FlightOption` times;
mock flight times; a planner UI at `/plan` and `/plan/[tripId]` — meeting
intake (form, with a paste-to-interpret box), "Find itineraries", ranked plan
cards showing rationale, soft violations, and risk, then select → book.
One traveler, two or three meetings, two domestic cities.

**Out, deliberately:**

- **Calendar integration.** The meetings table is the seam; a calendar
  connector writes rows into it and nothing else changes. That is the point of
  putting meetings in their own table rather than a blob on `trips`.
- **International** — visas, passport validity, timezone lead-time. The
  checker list is the seam, described above.
- **A real risk feed.** Risk is itinerary-derived only. An external
  intelligence feed is additive, and the synthesis layer is where it would land.
- **Multi-traveler / group trips.** One employee per plan.
- **Hotels in the constraint model.** Duffel Stays needs a geocoder that does
  not exist here; hotels stay on the mock and outside the solver. An overnight
  gap therefore shows up as a *risk factor*, not as a booked hotel.
- **Replacing the chat agent.** The planner is a new surface beside it. The
  booking/policy/disruption specialists overlap the planner and reconciling
  them is a follow-up — ripping out working code to prove a new idea is not
  how this earns its place.

## Sub-project boundary

This spec ends at: a traveler describes their meetings, in prose or on a form;
the system enumerates every itinerary that actually satisfies them; a model
ranks those and explains the trade-offs and the duty-of-care picture in the
traveler's own terms; the traveler selects one and it books at a price that
was re-verified with the supplier first. If no itinerary satisfies the
constraints, they are told which constraint is blocking and what would unblock
it.

Calendar, international, and the chat/planner reconciliation are named
follow-ups with their seams built, not part of this slice.
