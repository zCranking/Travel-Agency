# Real Duffel Integration — status

Replaces the mock-only travel layer with a live Duffel client, and closes the
gap where `create_booking` wrote `booked` rows that had never been booked with
any supplier.

## Built

- **`RealDuffelClient`** (`api/travel/duffel_client.py`) — `POST
  /air/offer_requests?return_offers=true` for search, `POST /air/orders` for
  ticketing, `Duffel-Version: v2`. Selected by `get_duffel_client()` from
  `DUFFEL_ACCESS_TOKEN`; blank token keeps the mock. Money is parsed with
  `Decimal`, never float.
- **Live-booking guard** — a token not prefixed `duffel_test_` is treated as
  live and refuses to create an order unless `DUFFEL_ALLOW_LIVE_BOOKING=true`.
  Unrecognised prefixes fail closed.
- **`issue_ticket()`** (`api/travel/ticketing.py`) — the single place a booking
  becomes real. Called by both `create_booking` (in-policy path) and
  `POST /bookings/{id}/approve` (manager path), always *before* the row is
  written, so a supplier failure leaves no phantom `booked` record. Approve is
  idempotent — a second approve does not buy a second ticket.
- **`employees.traveler_profile` jsonb** (migration `…0005`) — Duffel passenger
  fields (given/family name, born_on, gender, title, phone). Seeded for all
  four demo employees. Contains PII; covered by the existing RLS policies.
- **Fail-closed cabin mapping** — an offer whose cabin can't be read maps to
  `first` (highest fare rank) so it routes to approval rather than silently
  passing a fare-class check as economy. `first` added to `_FARE_RANK`, which
  previously would have raised `KeyError` on any Duffel first-class offer.
- **Offer cache + `UnknownOfferError`** — the agent re-types options into
  `create_booking` and, in live testing, invented the offer id
  (`frontier-sfo-jfk-2026-09-11`) and dropped `passenger_ids`. `book()` now
  resolves the offer from `_OFFER_CACHE` (populated at search) and refuses
  anything never offered. The supplier's confirmation, not `details`, sets the
  stored price.
- **No mock fallback in the real client** — previously an option with no
  `passenger_ids` silently mock-booked, stamping a fake `WF********` code on a
  row marked `booked`. That was the phantom booking this work exists to
  prevent; flights now raise instead.
- **`DuffelAPIError` carrying Duffel's message** — `raise_for_status()` alone
  gave "422 Unprocessable Entity" and dropped "offer no longer available".
- **Expected failures returned, not raised** — LangGraph's default tool-error
  handler only catches `ToolInvocationError` and re-raises everything else,
  which would 500 the chat. `search_travel`/`create_booking` return the
  message instead; the agent then re-searches on its own.
- **Order timeout + reconciliation** — ticketing uses a 180s timeout (search
  60s); on timeout the client looks the order up by offer id rather than
  retrying, since a timeout says nothing about whether the ticket was issued.
- **`tests/conftest.py`** blanks `DUFFEL_ACCESS_TOKEN` for the suite — without
  it, a developer's real token made unit tests build a real client and hit the
  network.
- **Tests** — 62 passing, ruff clean.

## Live-verified (test mode, 2026-07-29)

Real Duffel calls, not mocks:
- Search SFO→JFK returned real carriers/prices (Frontier, BA, Iberia, AA).
- Full agent path booked British Airways → PNR `435TUI`, matching a real order
  in the Duffel dashboard.
- The agent hit a genuinely stale Frontier offer mid-booking, read the returned
  error, and re-booked the next cheapest fare unprompted.
- Frontier/Travelport offers go stale within *seconds*, not the ~20–30 min the
  docs imply — the approval-time reprice gap below is therefore real today.

## Deliberately not built

- **Duffel Stays (real hotels).** Stays takes `geographic_coordinates` +
  radius, not a city name, so it needs a geocoder the agent doesn't have.
  `search_hotels` delegates to the mock. Add when a geocoding step is worth it.
- **Re-search/reprice at approval time.** Duffel offers expire ~20–30 min after
  search, so an approval arriving the next morning cannot ticket the held fare.
  Currently surfaces as a `409` telling the manager to have the traveler search
  again — honest, but a real TMC would reprice. Build when approval latency
  starts costing bookings.
- **Real disruption feed.** `get_disruption` still uses the deterministic mock.
- Multi-passenger orders, seat selection, ancillaries, cancellations/refunds.

## Manual follow-ups (not code)

Done as of 2026-07-29: migration `…0005` applied to the live Supabase project,
traveler profiles seeded, `DUFFEL_ACCESS_TOKEN` set (test token), end-to-end
booking verified.

Still open:
1. **Before ever setting a `duffel_live_*` token**, re-read the approval path —
   with real money, the reprice gap and the timeout-ambiguity window stop being
   theoretical. `DUFFEL_ALLOW_LIVE_BOOKING` is the deliberate speed bump.
2. `_OFFER_CACHE` is process-local; it must move to Redis/Postgres before the
   API runs more than one worker, or booking breaks under a load balancer.
3. The seeded `traveler_profile` values are fabricated. Real travelers need
   real passport/DOB data, which is regulated PII — see the build plan's §5
   data-privacy note before collecting any.
