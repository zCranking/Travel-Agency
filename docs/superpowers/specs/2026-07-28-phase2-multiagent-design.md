# Phase 2 + code-buildable Phase 3/4 slices — Design

> Source: `ai-native-corporate-travel-agency-buildplan.md` §4 Phase 2-4.
> Builds directly on `docs/superpowers/specs/2026-07-27-foundation-mvp-design.md`
> (already shipped, live-tested against real Supabase/Anthropic/Voyage infra).

## Scope honesty, up front

The buildplan's Phase 2-4 mix code and business/legal work. This spec covers
**only what's actually software**:

- Phase 2: multi-agent split, duty-of-care view, real RAG policy wiring,
  eval harness, LangSmith tracing. NOT covered: "bring on 3-6 SMB clients"
  (sales, not code).
- Phase 3: extracting a versioned, API-key-gated external boundary around
  the agent stack (the technical seam licensing requires). NOT covered:
  SOC2 Type 1 (external audit + Vanta/Drata purchase), Spotnana migration
  (vendor contract + business decision), actual licensing deals.
- Phase 4: an expense-platform sync adapter (mocked, same pattern as
  `MockDuffelClient`). NOT covered: SOC2 Type 2, enterprise sales motion,
  deeper NDC/GDS content (needs a real Spotnana partnership).

No fake second tenant is invented to justify Phase 3's API boundary — it's
built as the correct seam regardless of how many consumers exist today,
consistent with Task 8's existing routes.

## Phase 2: Multi-agent split

Replace the single agent node (`api/agent/graph.py`) with a supervisor that
routes to three specialist nodes, all still Claude Sonnet, all still plain
LangGraph tool functions (no MCP — same deviation as Phase 1, still holds:
three specialists is not yet enough surface to justify protocol overhead).

- **`booking_agent`** — today's agent, scoped down to search + book. Tools:
  `search_travel`, `check_policy` (quick rules check only), `create_booking`.
- **`policy_agent`** — dedicated to "is this in policy / why" questions.
  Tools: `check_policy`, `why_out_of_policy`. This is where Phase 1's
  already-built-but-barely-exercised RAG (`policy/retrieval.py`) actually
  gets used in anger.
- **`disruption_agent`** — NEW. Given a trip, checks its bookings for
  disruptions and offers rebooking. Duffel has no real disruption feed to
  poll (still mocked), so this is an on-demand check
  (`check_disruptions(trip_id)` tool), not a background poller — the
  buildplan itself says skip Temporal/cron until reliability requirements
  justify it, and an on-demand button demonstrates the capability without
  inventing infrastructure nothing yet needs. `MockDuffelClient` gains a
  `get_disruption(booking_id)` method returning `None` normally and a
  synthetic delay/cancellation for a specific seeded booking, so the path is
  actually exercisable end to end.
- **Supervisor** — a routing node (cheap classification prompt or simple
  keyword heuristic — implementer's call, whichever is less code) that picks
  which specialist handles each turn, then hands back to the user. Trip
  thread history and `trip_id`/`rules`/`policy_id` context still flow through
  exactly as today (`routes/chat.py`'s existing context-injection stays).

## Phase 2: Duty-of-care view

New page `/duty-of-care` (manager-only, no separate role system yet — same
"any signed-in employee can act as a manager" simplification the itinerary
page already uses) and backend `GET /duty-of-care` aggregating: every
employee, their upcoming/active trip (if any), that trip's bookings, and a
**mocked** destination risk level (`low`/`medium`/`high`, deterministic from
destination string hash — no real Riskline feed, clearly labeled as
placeholder data in the UI, not presented as real risk intelligence). This is
the "where are my people right now" view the buildplan calls for as a
differentiator against spreadsheet-and-email travel management.

## Phase 2: Eval harness

`api/evals/` — a fixed set of 15-20 hand-written scenarios (input message(s),
expected tool call and/or expected booking status/policy verdict), run via
`api/evals/run.py` against the real agent graph (requires `ANTHROPIC_API_KEY`,
skips cleanly without one same as the existing live-agent smoke test
pattern). Prints a pass/fail scorecard. Scoped down from the buildplan's
30-50 to a lazy-but-real 15-20 for a solo project — enough to catch
regressions on prompt/model changes, not a research benchmark.

## Phase 2: Observability

Wire LangSmith tracing: `LANGSMITH_API_KEY`/`LANGSMITH_TRACING` env vars,
same optional/lazy pattern as every other key in this repo (unset = tracing
off, no crash). Zero infrastructure — LangSmith is hosted, free tier covers
this project's volume. Self-hosted Langfuse is explicitly skipped: it needs
Docker, which this machine doesn't have (same constraint noted in the
sibling chronologix project's setup plan) — documented as a follow-up if
self-hosted observability is ever preferred over LangSmith's hosted tier.

## Phase 3 (code slice): external agent API boundary

Version the API under `/v1/`, add a `licensees` table (id, name, api_key,
created_at) and a FastAPI dependency that checks `X-API-Key` against it,
applied to a new externally-consumable route
`POST /v1/agent/message` (thin wrapper around the same booking flow, scoped
to a `licensee_id` instead of trusting an open `trip_id`). The existing
`web/` frontend becomes licensee zero, seeded alongside Acme Corp — this is
the real technical seam Phase 3 licensing requires, proven by our own
frontend consuming it, not a speculative feature for an imaginary second
company.

## Phase 4 (code slice): expense-platform sync adapter

`api/expense/sync_client.py` — same pattern as `travel/duffel_client.py`:
an interface (`sync_booking(booking) -> SyncResult`) with a
`MockExpenseSyncClient` today, swappable for a real Ramp/Brex/Concur SDK
later behind the same interface. Wired as a no-op-if-unconfigured call after
`create_booking` lands a `booked` row (never blocks the booking itself on
sync success/failure).

## Testing

Same standard as Phase 1: pytest for all new deterministic logic (routing
heuristic, disruption mock, duty-of-care aggregation, licensee auth
dependency, expense sync mock), one live-agent smoke test extension for the
new specialist routing (gated behind `ANTHROPIC_API_KEY`, skips cleanly),
manual browser check for `/duty-of-care`.

## Explicitly out of scope (business/legal, not code)

Client acquisition, SOC2 Type 1/2, entity formation, seller-of-travel state
registration, E&O insurance, host-agency accreditation agreement, Spotnana
contract negotiation, enterprise sales motion. These remain open items for
the human founder — no amount of code closes them.
