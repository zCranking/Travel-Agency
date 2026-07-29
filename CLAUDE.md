# CLAUDE.md

## Tech stack
FastAPI (Python 3.13) + LangGraph backend in `api/`, owns all Claude/Duffel/Voyage
calls. Next.js (TypeScript, App Router) + Tailwind + shadcn/ui frontend in `web/`.
Supabase (Postgres + pgvector, Auth) for data. One seeded demo company ("Acme Corp").

## Commands
```bash
# api/ (from repo root)
cd api && .venv/Scripts/python.exe -m uvicorn main:app --reload   # dev server
cd api && .venv/Scripts/python.exe -m pytest                      # test
cd api && .venv/Scripts/python.exe -m ruff check .                # lint

# web/ (from repo root)
npm run dev --prefix web
npm run lint --prefix web
npm run build --prefix web

# supabase/ (from repo root)
npx supabase db push
```

## Architecture (one paragraph, not a tour)
Employees log into `web/` (Supabase Auth) and chat with a LangGraph agent
(`api/agent/`) that routes to a booking/policy/disruption specialist and calls
`search_travel` (`api/travel/duffel_client.py`), `check_policy` (hardcoded rules
first, `api/policy/rules.py`, then pgvector-backed RAG over the uploaded policy
PDF, `api/policy/retrieval.py`, when the "why" matters), and `create_booking`,
which writes a `bookings` row as `booked` or `pending_approval`. `web/`'s
itinerary page reads bookings and lets a manager approve/reject pending ones.
Nothing in `web/` calls Claude, Duffel, or Voyage directly.

## Duffel
`get_duffel_client()` returns `MockDuffelClient` when `DUFFEL_ACCESS_TOKEN` is
blank and `RealDuffelClient` (live REST API) when it is set — flights only;
hotels and disruptions still delegate to the mock because Duffel Stays needs
lat/long, not a city name. Anything that marks a booking `booked` must go
through `issue_ticket()` (`api/travel/ticketing.py`) — both `create_booking`
and the manager approve endpoint do — so `booked` always means a real supplier
confirmation. Ticketing happens *before* the row is written/updated. A
`duffel_live_*` token additionally requires `DUFFEL_ALLOW_LIVE_BOOKING=true`
before any order is created; unrecognised token prefixes are treated as live.

Three rules live testing proved necessary — don't undo them:
- **Never trust the model's copy of an offer.** The agent re-types options into
  `create_booking` and will invent offer ids and drop `passenger_ids`. Search
  caches offers in `_OFFER_CACHE`; `book()` resolves by id from there and
  raises `UnknownOfferError` for anything never offered. Price comes from the
  supplier's confirmation, not from `details`.
- **`RealDuffelClient` must never fall back to the mock for a flight.** A
  `WF********` code on a `booked` row is a phantom booking.
- **Expected supplier failures are returned, not raised.** LangGraph's default
  tool-error handler re-raises anything that isn't a `ToolInvocationError`,
  which 500s the chat. `search_travel`/`create_booking` return the message so
  the agent re-searches — it recovers from stale fares on its own this way.

## Conventions
- One demo company only in this build — do not add multi-tenant admin UI.
- No MCP tool-wiring layer yet — tools are plain Python functions bound into the
  LangGraph graph. Revisit if/when a second agent needs to share tool infra.
- UI changes go through the `frontend-design` skill, not generic shadcn defaults.
<!-- codeburn:begin read-edit-ratio -->
Before editing any file, read it first. Before modifying a function, grep for all callers. Research before you edit.
<!-- codeburn:end read-edit-ratio -->
