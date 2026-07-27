from travel.duffel_client import MockDuffelClient


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
