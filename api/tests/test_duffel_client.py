from datetime import datetime

from travel.duffel_client import MockDuffelClient
from travel.models import FlightOption


def test_search_flights_returns_varied_prices():
    client = MockDuffelClient()
    options = client.search_flights("SFO", "JFK", "2026-09-01")
    assert len(options) >= 3
    prices = {o.price_cents for o in options}
    assert len(prices) > 1  # varied, so policy checks have something to violate


def test_search_hotels_returns_options():
    client = MockDuffelClient()
    options = client.search_hotels("New York", "2026-09-01", "2026-09-03")
    assert len(options) >= 3
    assert all(o.nightly_rate_cents > 0 for o in options)


def test_book_returns_confirmation():
    client = MockDuffelClient()
    option = client.search_flights("SFO", "JFK", "2026-09-01")[0]
    confirmation = client.book(option)
    assert confirmation.confirmation_code
    assert confirmation.price_cents == option.price_cents


def test_flight_option_carries_instants_and_defaults_to_blank():
    bare = FlightOption(
        id="x", airline="United", fare_class="economy", origin="SFO",
        destination="ORD", depart_date="2026-09-01", price_cents=31000,
    )
    assert (bare.depart_at, bare.arrive_at, bare.stops) == ("", "", 0)

    timed = FlightOption(
        id="x", airline="United", fare_class="economy", origin="SFO",
        destination="ORD", depart_date="2026-09-01", price_cents=31000,
        depart_at="2026-09-01T07:30:00-07:00",
        arrive_at="2026-09-01T13:45:00-05:00",
        stops=1,
    )
    assert timed.depart_at.endswith("-07:00")
    assert timed.stops == 1


def test_mock_flights_have_usable_instants():
    """The planner has to demo and test with no Duffel token, so the mock must
    supply times the solver can reason about."""
    options = MockDuffelClient().search_flights("SFO", "ORD", "2026-09-01")

    for option in options:
        depart = datetime.fromisoformat(option.depart_at)
        arrive = datetime.fromisoformat(option.arrive_at)
        assert depart.tzinfo is not None and arrive.tzinfo is not None
        assert arrive > depart
        assert depart.date().isoformat() == "2026-09-01"

    # spread across the day, so a presence window can actually discriminate
    assert len({o.depart_at for o in options}) == len(options)
