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
- **Tests** — 51 passing, ruff clean. Covers offer mapping, Decimal money
  conversion, the cabin fallback, the live-token refusal (asserting nothing
  hits the network), traveler lookup, ticket-before-insert, and no-row-on-
  ticketing-failure.

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

1. Apply migration `00000000000005_traveler_profile.sql` to the live Supabase
   project, then re-run `api/scripts/seed.py` to populate traveler profiles.
   Note `00000000000004_companies_rls.sql` was still uncommitted/unapplied as
   of this work — check it landed first.
2. Put the Duffel token in `api/.env` as `DUFFEL_ACCESS_TOKEN=…` and restart
   the API. Verify with a real search before trusting a booking.
3. Live-verify: search SFO→JFK through the chat UI and confirm real airline
   names/prices come back, then book one in test mode and check the order
   appears in the Duffel dashboard.
