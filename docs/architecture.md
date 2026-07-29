# Architecture

Two front doors onto one booking core.

## Request flow — planner (the primary surface)
1. Employee authenticates via Supabase Auth in `web/` and starts a trip
   (`POST /trips`).
2. They state their meetings — typed on the form, or pasted as prose and
   drafted by `POST /trips/{id}/interpret`. **A draft is never persisted
   without the traveler confirming it.**
3. `POST /trips/{id}/plan` builds a `TripIntent`, runs `planning.solver.solve`
   to enumerate itineraries satisfying every hard constraint, persists them,
   then has `judge` rank them and `risk` assess them. If nothing is feasible it
   returns the binding constraint and a relaxation, never a bare empty list.
4. `POST /itineraries/{id}/select` re-searches every leg, matches it to the
   stored schedule, and books through `create_booking` -> `issue_ticket()`. Any
   price increase or missing leg needs explicit confirmation first.

## Request flow — chat (still live, unchanged)
1. `web/` opens/continues a trip thread and POSTs messages to `api/routes/chat`.
2. The LangGraph agent (Claude Sonnet) routes to a booking/policy/disruption
   specialist and calls `search_travel`, `check_policy`, `create_booking`,
   persisting to `trip_messages` and `bookings`.
3. `web/`'s itinerary page reads `bookings` and shows approve/reject actions
   for `pending_approval` rows.

## Module boundaries
- `api/planning/` — the constraint planner. `models.py` (timezone-aware,
  integer-cents domain types), `checkers.py` (hard/soft constraints as two
  pluggable lists), `solver.py` (a pure function with search injected),
  `interpret.py`/`judge.py`/`risk.py` (the AI layers, each with a
  deterministic fallback).
- `api/travel/` — live Duffel flights (`RealDuffelClient`) or fixtures
  (`MockDuffelClient`) behind one `search_flights`/`search_hotels`/`book`
  method set. Hotels and disruptions still use the mock: Duffel Stays needs
  lat/long, not a city name. `ticketing.py` is the single place a booking
  becomes real.
- `api/policy/` — `rules.py` (deterministic, cheap) then `retrieval.py`
  (pgvector RAG over the policy PDF) for "why" explanations.
- `api/agent/` — the LangGraph graph and its tool bindings.
- `api/routes/` — thin HTTP adapters. Nothing in `web/` calls Claude, Duffel
  or Voyage directly.
- `supabase/migrations/` — the single source of truth for schema.

## Where the AI is, and isn't
Load-bearing: reading messy meeting descriptions into structured constraints;
choosing among feasible plans that trade cost, comfort, risk and policy against
each other and saying why; explaining infeasibility as something actionable;
synthesising mechanical risk factors into one duty-of-care call.

Deliberately absent: searching, pricing, picking dates, evaluating policy,
computing totals, and booking. Code does all of that, because a form plus a
rules engine does it better — which was the whole reason for the planner
pivot. See `docs/superpowers/specs/2026-07-29-constraint-planner-design.md`.

## Deviations from the strategy doc (intentional, see specs)
- No MCP layer for tool wiring — tools are plain Python functions bound into
  the graph. Revisit when a second agent needs to share tool infra.
- No Temporal, Langfuse, multi-tenant admin, or SOC2 work in this build.
- Duffel is live for flights in **test mode**; a `duffel_live_*` token
  additionally requires `DUFFEL_ALLOW_LIVE_BOOKING=true`.
