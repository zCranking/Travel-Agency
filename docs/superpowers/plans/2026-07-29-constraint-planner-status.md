# Constraint Planner — status

Implements `docs/superpowers/specs/2026-07-29-constraint-planner-design.md`.
Supersedes the guided-booking-wizard spec and plan, which were never executed.

## Why this exists

The agent was a natural-language front end over three structured tool calls.
The wizard spec proved it by accident: it reimplemented the whole booking flow
with no model in the loop and lost nothing. If a form can replace the agent,
the agent was decoration.

The planner does a job a form cannot: the input is under-specified,
over-constrained, and requires trading conflicting objectives against each
other. There is no single correct query — there is a feasible set and a
judgment call.

## Built

- **`meetings` and `itineraries` tables** (migration `…0007`, applied), plus
  `trips.origin_city`, `trips.budget_cents`, `employees.travel_preferences`.
  RLS on with no policy — default-deny for anon/authenticated, same as
  `bookings`; both tables are read through the service role only.
- **Flight instants** — `FlightOption` gained `depart_at`/`arrive_at` (ISO 8601
  with offset) and `stops`. `_leg_times()` stitches Duffel's naive local
  segment times to the IANA zone on the airport object; neither half is usable
  alone. Verified against live Duffel: `SFO 10:01-07:00 → ORD 20:15-05:00`.
  The mock returns a fixture schedule so the planner demos with no token.
- **`planning/models.py`** — timezone-aware, integer-cents domain types.
  Validation at the boundary: a naive datetime or a city-less in-person meeting
  fails where a human can read the message, not four frames into the solver.
- **`planning/checkers.py`** — hard and soft constraints as two pluggable
  lists, all sharing `(itinerary, intent) -> list[Violation]`. Presence uses a
  *buffered* transit window (an hour from landing is not "there"); no-fly uses
  raw airborne time (a call can be taken from a lounge). One `flexible` flag
  covers both modes and defaults to binding.
- **`planning/solver.py`** — a pure function with `search` injected, so
  feasibility is table-tested against fixtures with no network. Derives the
  city sequence and presence windows, searches the deadline date *and the day
  before* (an early meeting is reached by flying the night before), prunes the
  cartesian product as it goes, ranks by price and caps at five.
- **Binding-constraint diagnosis** — when nothing is feasible it relaxes one
  hard constraint at a time and reports the one actually blocking, with a
  suggested relaxation. An empty list is the one answer a traveler can do
  nothing with.
- **`interpret` / `judge` / `risk`** — each with a deterministic fallback, so a
  misbehaving model degrades output quality and never 500s an endpoint.
  `judge` validates every itinerary id against the ids the solver produced
  (the Duffel offer-cache rule generalised) and falls back to price order.
  `risk` extracts factors in code and only asks the model to synthesise them —
  no factors means no model call at all.
- **Endpoints** — `POST /trips`, meetings CRUD, `/interpret`, `/plan`,
  `/itineraries/{id}/select`. `company_id` is resolved server-side on trip
  creation, never taken from the request.
- **Reprice at selection** — re-searches each leg, matches on carrier and
  departure instant, and books from the *fresh* offer. Any price increase or a
  vanished leg needs explicit confirmation; a decrease books straight through.
  Ticketing still goes through `create_booking` → `issue_ticket()`.
- **Itinerary-derived duty-of-care risk** — `/duty-of-care` now prefers the
  assessment on the selected itinerary and reports `risk_source` as
  `"itinerary"` or `"placeholder"`, so the UI can never present the
  destination hash as intelligence.
- **Planner UI** — `/plan` and `/plan/[tripId]`: meeting intake with a
  paste-to-interpret box, ranked plan cards with rationale, soft-violation
  badges and an auditable risk block, and select → reprice → book.
- **Tests** — 135 passing, ruff clean.

## Live-verified (test mode, 2026-07-29)

Real Duffel search, three real meetings across two cities:

```
5 feasible itineraries
  $290
    SFO->ORD Duffel Airways    Sun 09/13 09:17 -> 15:49
    ORD->DEN Iberia            Tue 09/15 10:50 -> 12:19
    DEN->SFO American Airlines Thu 09/17 12:23 -> 14:02
  $291  ... ORD->DEN Frontier  Tue 09/15 22:40 -> 00:29
    flag: red_eye - ORD->DEN departs 22:40 local.
```

It flew out the night before for a 2pm Monday pitch, kept the ORD→DEN hop
after the binding 9am Tuesday board call rather than during it, and flagged
the red-eye as a soft violation instead of hiding the option.

## Deliberately not built

- **Calendar integration.** The `meetings` table is the seam — a connector
  writes rows into it and nothing else changes. That is why meetings are a
  table and not a blob on `trips`.
- **International.** Visas, passport validity, timezone lead-time. The seam is
  `HARD_CHECKERS`: append `check_visa`/`check_passport_validity` and the
  solver, the infeasibility search and the UI all pick them up unchanged.
  `GROUND_BUFFER`/`AIRPORT_LEAD` are domestic figures and will need
  international counterparts.
- **A real risk feed.** Risk is itinerary-derived only — every factor is a
  mechanical property of the plan. An external intelligence feed is additive,
  and `risk.synthesize` is where it would land.
- **Hotels in the constraint model.** Duffel Stays needs a geocoder that
  doesn't exist here, so hotels stay on the mock and outside the solver. An
  overnight therefore surfaces as the `overnight_gap` *risk factor* ("no hotel
  booked"), not as a booking.
- **Multi-traveler / group trips.** One employee per plan.
- **Reconciling the chat agent with the planner.** Both exist. The
  booking/policy/disruption specialists overlap the planner, and the agent has
  no idea what the planner booked. Ripping out working code to prove a new
  idea is not how the planner earns its place; reconcile once the planner has
  actually displaced the chat in use.

## Follow-ups

1. **`_stays()` keys presence windows by city**, so a trip that visits one city
   twice merges both stays into a single window. Fine for the two-or-three
   meeting trips this slice targets; key by `(city, hop index)` when a real
   revisit shows up. Marked with a `ponytail:` comment in `solver.py`.
2. **`_OFFER_CACHE` is still process-local** (from the Duffel work). Reprice-
   at-selection repopulates it on the same worker that then books, so the
   planner path is safe today — but it must move to Redis/Postgres before the
   API runs more than one worker.
3. **`tzdata` is now a hard dependency.** Windows ships no system tz database,
   so `zoneinfo` cannot resolve IANA keys without it. Added to
   `api/pyproject.toml`.
4. **The planner does not book hotels**, so a multi-night trip books flights
   only. Either integrate Stays behind a geocoder or make the overnight
   advisory louder in the UI.
