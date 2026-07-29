# Guided Booking Wizard — Design

> Builds on `docs/superpowers/specs/2026-07-27-foundation-mvp-design.md` (chat +
> itinerary, live) and `docs/superpowers/specs/2026-07-28-phase2-multiagent-design.md`
> (multi-agent split, duty-of-care, licensing seam, all live). This spec adds a
> second, non-chat way to book a trip.

## Goal

Today the only way to book a trip is a free-text chat conversation with the
LangGraph agent — and even that has no real entry point in the UI (every
existing link opens an *already-seeded* trip's thread; there is no "start a
new trip" button anywhere). This spec adds:

1. A **"Plan a trip" entry point** (Home + Trips pages) that lets the
   employee actually start a new trip.
2. A choice between **chat** (existing) and a **guided step-by-step wizard**
   (new) — a stepper-driven flow: Trip basics → Flight → Hotel (skippable) →
   Review.
3. A way to **switch between the two modes at any time** for the same trip.

## Why this doesn't touch the agent

`docs/superpowers/specs/2026-07-27-foundation-mvp-design.md`'s own stated
design intent: *"keep the agent's tool layer (`search_travel`, `check_policy`,
`create_booking`) decoupled from any one front door. The web chat is one
adapter calling into that layer; Slack/email/Teams would be additional
adapters calling the same agent and tools, not a rewrite."*

The wizard is exactly that: a second adapter. It calls the same three
tool-layer functions directly, through new plain FastAPI endpoints — no LLM
round-trip per step. This keeps each wizard step instant and deterministic,
and avoids the fragility of parsing a free-text agent reply into structured
UI state.

## Architecture & data flow

```
Home/Trips ("Plan a trip")
        │
        ▼
     /plan                       ── mode choice, no trip created yet
        │
        ├── pick "Guided" ─┐
        │                  ▼
        │            POST /trips  (creates the trip row)
        │                  │
        │                  ▼
        │            /plan/{tripId}   ── stepper: basics → flight → hotel → review
        │                  │
        │                  │  (header button, always available)
        │                  ▼
        │            /chat/{tripId}  ←──────────────┐
        │                  ▲                        │
        └── pick "Chat" ───┘                 (header button, always available)
                            │
                     POST /trips  (creates the trip row, same endpoint)
```

Both modes write to the same `trips`/`bookings` tables via the same
`create_booking` logic, so switching modes needs no state hand-off — whatever
already exists for that `trip_id` is just there when the other mode loads.

## Backend additions

All new, all thin wrappers around existing tool-layer functions
(`api/agent/tools.py`). No LangGraph, no Claude call, in any of them.

### `POST /trips` (new file `api/routes/trips.py`)
Body: `{employee_id: str}`. Looks up the employee's `company_id` server-side,
creates a `trips` row with a fresh `thread_id` (same `uuid4()` pattern
`seed.py` already uses), returns `{id}`. This is the only way today to create
a trip outside of `seed.py` — both new UI entry points route through it.

### `GET /trips/{trip_id}/search` (same new file)
Query params: `kind`, `origin_or_location`, `destination`, `date` — same
shape `search_travel` already takes. Calls it directly (unwraps the
`@tool`-decorated function) and returns `[o.model_dump() for o in options]`.
`trip_id` isn't actually used inside (search doesn't depend on the trip) but
keeps the route trip-scoped, matching every other route's shape
(`/trips/{id}/bookings`, `/trips/{id}/messages`).

### `POST /trips/{trip_id}/bookings` (added to existing `api/routes/bookings.py`)
Body: `{kind, details}`. Looks up the trip's company rules (see helper below),
calls `create_booking(trip_id, kind, details, rules)` directly, returns
`{id, status, violations}` — the same booked/pending_approval decision chat
already produces, because it's the same function.

### Shared rules-lookup helper
`routes/chat.py`'s `handle_chat_message` already does a trip → `company_id` →
`policies` → `rules` lookup inline. Extracting this into
`policy/rules.py::get_trip_rules(db, trip_id) -> tuple[str, dict]` (returns
`policy_id, rules`) so both `chat.py` and the new bookings endpoint call the
same three-line lookup instead of it existing in two places.

### `main.py`
Register the new `trips_router`.

## Frontend additions

### `/plan` — mode chooser
Two cards, "Guided" and "Chat" (no trip exists yet at this point). Picking
either calls `POST /trips` with the signed-in employee's id (resolved the
same way `home`/`itinerary` already do — `auth.getUser()` →
`employees` row by `auth_user_id`), then routes to `/plan/{id}` or
`/chat/{id}`.

### `/plan/[tripId]` — the wizard
Steps, each a section of one client page component (not four separate
route files — the whole wizard is one page with step state, matching how
`itinerary/page.tsx` already manages a single page with internal
queue/detail state):

1. **Trip basics** — origin, destination, depart date, return/check-out
   date. Local state only, nothing persisted yet.
2. **Flight** — calls `GET /trips/{tripId}/search?kind=flight&...`, renders
   results with a new `OptionCard` component (a selection-list sibling to
   the existing `BookingCard`, which is for already-booked items and expects
   a `status`). Picking one holds it in local state; nothing written yet.
3. **Hotel** — same shape, `kind=hotel`. Has a "Skip hotel" action.
4. **Review** — shows both chosen items (or just the flight, if hotel was
   skipped). "Confirm and book" calls `POST /trips/{tripId}/bookings` once
   per item, sequentially, and shows each one's real returned status
   (`booked` / `pending_approval`) — the same visual language
   (`BookingCard` + status stamp) the itinerary page already uses, so a
   pending item here looks like a pending item everywhere else in the app.

A stepper across the top shows all four stages with filled/active/upcoming
states, styled with the existing amber/teal/ink palette — same visual
language as the rest of the app, not a new design system. `AppShell`'s
`title` prop is currently typed `string`; widen it to `React.ReactNode` (a
one-line type change, no other caller is affected since they all already
pass plain strings) so `/plan/[tripId]` can pass the stepper component in
that slot instead of adding a parallel header mechanism.

### Switch buttons
Both `/plan/[tripId]` and `/chat/[tripId]` get a button in the `AppShell`
header `actions` slot linking to the other mode for the same `tripId`.
Available at every step, per your answer — since nothing needs to be handed
off, this is just a `Link`.

### Entry points
"Plan a trip" button added to: Home's hero area (next to/near the existing
"Review trips" pill) and the Trips (`/itinerary`) page header (via its
existing `actions` slot, same slot the filter pills already use).

## Deliberately deferred

- **No step-resumption.** If you switch modes on a trip that already has
  bookings from the other mode, the wizard always starts at step 1 rather
  than detecting "a flight already exists, skip to hotel." The Review step
  will still show whatever already exists once you get there, so nothing is
  lost or duplicated — it's just not a smart resume.
- **Chat doesn't know what the wizard already booked.** The agent has no
  "list this trip's current bookings" tool today, so if you book a flight in
  the wizard then switch to chat, the agent won't proactively mention it
  unless the employee tells it. Both are flagged, real, and out of scope for
  this slice per your go-ahead to proceed with the design as presented.

## Testing

- Pytest for the three new endpoints: trip creation (row shape, company_id
  resolution), search passthrough (mocked `search_travel`), and booking
  creation status logic (reuses the existing booked/pending_approval test
  coverage pattern already used for `create_booking`).
- Manual browser check (per this workspace's standing convention) of both
  golden paths before calling this done: guided booking end-to-end (basics →
  flight → hotel → review → booked), and switching chat → guided → chat on
  the same trip without losing anything.

## Sub-project boundary

This spec ends at: an employee can start a brand-new trip from the UI (which
did not exist before this slice), choose guided or chat, complete a booking
through the guided wizard entirely via deterministic endpoints, and switch
between both modes freely for the same trip. Smart resumption and
agent-visible wizard bookings are noted follow-ups, not part of this slice.
