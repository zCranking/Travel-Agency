# Wayfare AI Travel Assistant — Foundation + Phase 1 MVP Design

> Working name `wayfare-ai` — rename anytime, not load-bearing.
> Source strategy doc: `ai-native-corporate-travel-agency-buildplan.md` (repo root).
> This spec covers the FIRST buildable slice of a multi-phase project. Later phases
> (multi-agent + duty-of-care, licensing/SOC2, scale) get their own spec/plan cycles.

## Relationship to other projects
This is a brand-new, separate project from `Corporate-Travel-Agent` (an already-shipped
T&E-compliance showcase). No code or data is shared between them.

## Goal
A working single-company travel-booking assistant: an employee logs in, chats with an
AI agent to search and book flights/hotels, gets policy-aware recommendations, and sees
bookings in an itinerary view — with booking creation actually enforced against policy
(rules + retrieval) and routed to human approval when out-of-policy or above a dollar
threshold. Duffel is stubbed with realistic fixture data (no real API key yet); real
Duffel wiring is a drop-in swap behind the same interface later.

UI quality is a first-class requirement, not polish-after: the chat and itinerary
surfaces must look and feel like a considered product, not generic component-library
defaults. Built using the `frontend-design` skill's guidance, not skipped.

## Architecture
Same repo shape as the chronologix-ai-starter-kit precedent:
- `api/` — FastAPI (Python 3.13), owns the LangGraph agent and all Claude/Duffel calls.
- `web/` — Next.js (TypeScript, App Router) + Tailwind + shadcn/ui, chat-first UI.
- `supabase/` — Postgres + pgvector schema migrations, Supabase Auth.

**Deviation from the buildplan (flagged, not accidental):** the buildplan recommends
MCP for tool wiring long-term. For one LangGraph agent with three tools, that's protocol
overhead with no swappability payoff yet. This build uses plain LangGraph-bound Python
tool functions. Revisit MCP when Phase 2 splits into multiple agents that need shared,
swappable tool infrastructure.

**Explicitly out of scope for this build** (correctly deferred per the buildplan's own
phasing, not omitted by accident): Temporal, Langfuse/LangSmith, multi-tenant admin,
real Duffel API keys, deployment/CI, SOC2.

## Components

### `api/agent/`
One LangGraph agent, Claude Sonnet as the reasoning model, three tools:
- `search_travel(query)` — flights + hotels, delegates to `travel/duffel_client.py`.
- `check_policy(booking_draft, employee_id)` — delegates to `policy/rules.py`, and
  `policy/retrieval.py` when the employee/agent asks "why" or the rule check is
  ambiguous.
- `create_booking(booking_draft, employee_id)` — writes to Postgres with a `status`
  of `booked` or `pending_approval`.

Conversation state is persisted per trip thread (one thread = one trip's chat history)
so a page reload doesn't lose context.

### `api/travel/duffel_client.py`
Interface: `search_flights(origin, destination, dates) -> list[FlightOption]`,
`search_hotels(location, dates) -> list[HotelOption]`, `book(option) -> BookingConfirmation`.
`MockDuffelClient` implements this now with realistic fixture data (a handful of
airlines/fare classes/hotel tiers, varied prices so policy checks have something to
actually violate). Swapping in the real Duffel SDK later means writing a
`RealDuffelClient` behind the same interface — no call-site changes.

### `api/policy/`
- `rules.py` — hardcoded-per-company config (JSON/dataclass): max fare class, max
  hotel nightly rate, advance-booking window, above which a booking needs approval.
  Deterministic, no LLM call, cheap — the agent checks this first.
- `retrieval.py` — the company's travel-policy PDF is chunked, embedded (Voyage AI
  `voyage-3`, 1024 dims — matches the chronologix precedent's choice, since Anthropic
  doesn't ship its own embeddings API) and stored in `policy_chunks` (pgvector). Used
  only when the agent needs to answer "why is this out of policy" with a cited clause,
  not for the initial check.

### Human-in-the-loop
A booking that fails a rule check or exceeds the dollar threshold lands as
`status = "pending_approval"` instead of `"booked"`. The itinerary view shows a plain
Approve/Reject action on pending items — no separate ops/TMC-staff persona in this
slice; the traveler's manager (a role on the employee record) approves.

### `web/`
- Supabase Auth (email/password) login.
- **Chat page** (primary surface) — conversational search/book flow.
- **Itinerary/dashboard page** (trust surface) — booked + pending trips, approve/reject.
- Built with the `frontend-design` skill invoked at build time; shadcn/ui as the
  component base (already a sane default, not a new heavyweight dependency), styled
  deliberately rather than left at defaults.

## Data model (Supabase)
- `companies(id, name)`
- `employees(id, company_id, auth_user_id, name, email, manager_employee_id)`
- `policies(id, company_id, rules jsonb, policy_doc_storage_path)`
- `policy_chunks(id, policy_id, content, embedding vector(1024))`
- `trips(id, company_id, employee_id, thread_id, created_at)`
- `bookings(id, trip_id, kind ['flight'|'hotel'], details jsonb, price_cents, status ['booked'|'pending_approval'|'rejected'], created_at)`
- `trip_messages(id, trip_id, role, content, created_at)` — chat transcript.

Seed data: one company ("Acme Corp"), 3-4 employees (including one manager), one short
real-feeling travel policy PDF, and the matching `rules` config.

## Data flow
Employee logs in → opens/starts a trip chat → agent calls `search_travel` → shows
options in-chat → employee picks one → agent calls `check_policy` (rules, then RAG if
ambiguous or "why" is asked) → `create_booking` → row lands as `booked` or
`pending_approval` → itinerary page reflects it; manager can approve/reject pending
items from there.

## Testing
- Pytest for `duffel_client` (mock), `policy/rules.py`, and the booking-status decision
  logic — deterministic, no LLM needed to verify the plumbing.
- One live-agent smoke test (search → policy-flagged booking → pending_approval),
  gated behind an `ANTHROPIC_API_KEY` env check so it skips cleanly without a key.
- Manual browser check of the chat + itinerary UI (golden path: book an in-policy
  trip; edge case: book an out-of-policy trip and see it land pending, then approve
  it) before calling any increment done — per this workspace's convention of verifying
  real usage, not just type-checking.

## Sub-project boundary
This spec ends at: a demo employee can log in, chat-book a flight/hotel against mock
Duffel data, have it checked against real rules + RAG policy, see it land booked or
pending, and a manager can approve it — all through a genuinely well-designed UI.
Multi-agent specialization, real Duffel keys, duty-of-care tracking, licensing
packaging, and SOC2 are separate future specs.

## Down-the-road ideas: reducing adoption friction

Not scoped, not scheduled — captured here so they aren't lost. The unifying thesis:
**the biggest adoption barrier for a company this size isn't the AI, it's asking
someone to open yet another tab and learn yet another tool.** Every idea below routes
Wayfare through a surface the company already has open, rather than adding a new one.
When any of these gets prioritized, it becomes its own spec — this is raw material for
that conversation, not a commitment.

- **Slack / Microsoft Teams bot as the primary interface.** `/book`, or just DM the bot
  in plain English — same LangGraph agent behind a chat-app adapter instead of (or
  alongside) the standalone web chat. This is plausibly the highest-leverage single
  addition: it means an employee never has to visit a separate app to book routine
  travel. Approvals could route the same way — a manager approves from a Slack message,
  not a login.
- **Email-native booking and approvals.** Forward a meeting invite or "need to be in
  Denver on the 12th" email to a dedicated address and the agent drafts options back in
  the same thread. Approvals-by-email (reply "approve" to a notification) for managers
  who live in their inbox, not Slack.
- **Calendar integration (Google Calendar / Outlook).** Read upcoming meetings to
  proactively suggest "you have an in-person client meeting in Austin next Tuesday —
  want me to find flights?" instead of waiting to be asked. Write confirmed itineraries
  back as calendar events with the confirmation/PNR attached, so the itinerary lives
  where people already check their day.
- **Expense-tool sync (Ramp, Brex, Expensify, Concur).** Push booking line items
  directly into the company's existing expense system instead of creating a second
  system of record travelers/finance have to reconcile against. This is also the
  natural on-ramp to the buildplan's later Stripe Issuing / virtual-card work.
- **SSO (Google Workspace / Microsoft Entra / Okta) instead of a standalone
  login.** Removes "yet another password" friction and is usually a hard requirement
  once a company has an IT department, not just a nicety.
- **HRIS integration (Rippling, Gusto, BambooHR).** Auto-provision employees/managers
  and their approval chain from the company's existing org chart instead of manual
  seeding — relevant once this moves past a single demo company.
- **"Reply to this thread" disruption handling.** When a flight is delayed/cancelled,
  notify the traveler in whatever channel they already used to book (Slack DM, email,
  SMS) with rebooking options one reply away, rather than requiring them to open the
  app mid-disruption.
- **Browser extension / right-click booking.** Highlight a meeting request or address
  in Gmail/Outlook and get a "book travel for this" action inline, skipping the
  navigate-to-a-new-tab step entirely.

The common design implication for the current architecture: keep the agent's tool
layer (`search_travel`, `check_policy`, `create_booking`) decoupled from any one
"front door." The web chat is one adapter calling into that layer; Slack/email/Teams
would be additional adapters calling the same agent and tools, not a rewrite.
