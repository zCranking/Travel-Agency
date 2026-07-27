# Architecture

## Request flow
1. Employee authenticates via Supabase Auth in `web/`.
2. `web/` opens/continues a trip thread and POSTs chat messages to
   `api/agent` endpoints.
3. The LangGraph agent (Claude Sonnet) calls `search_travel`, `check_policy`,
   and `create_booking` as needed, persisting messages to `trip_messages` and
   the resulting booking to `bookings`.
4. `web/`'s itinerary page reads `bookings` (via a thin FastAPI read endpoint)
   and shows approve/reject actions for `pending_approval` rows.

## Module boundaries
- `api/travel/` — Duffel integration, mock today, swappable for the real SDK
  behind the same `search_flights`/`search_hotels`/`book` interface.
- `api/policy/` — `rules.py` (deterministic, cheap) then `retrieval.py`
  (pgvector RAG over the policy PDF) for "why" explanations.
- `api/agent/` — the LangGraph graph and its tool bindings. Only module that
  calls Claude.
- `supabase/migrations/` — the single source of truth for schema.

## Deviations from the strategy doc (intentional, see spec)
- No MCP layer for tool wiring (one agent, three tools — not worth the
  protocol overhead yet).
- No Temporal, Langfuse/LangSmith, real Duffel key, multi-tenant admin, or
  SOC2 work in this build.
