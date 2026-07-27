from policy.rules import check_rules
from travel.models import FlightOption, HotelOption

RULES = {
    "max_fare_class": "economy",
    "max_hotel_nightly_rate_cents": 25000,
    "advance_booking_days_required": 3,
    "approval_threshold_cents": 150000,
}


def test_economy_fare_in_policy():
    flight = FlightOption(
        id="1", airline="Skyward Air", fare_class="economy",
        origin="SFO", destination="JFK", depart_date="2026-09-01",
        price_cents=30000,
    )
    result = check_rules(flight, RULES)
    assert result.in_policy
    assert result.violations == []


def test_business_fare_violates_max_fare_class():
    flight = FlightOption(
        id="2", airline="Skyward Air", fare_class="business",
        origin="SFO", destination="JFK", depart_date="2026-09-01",
        price_cents=90000,
    )
    result = check_rules(flight, RULES)
    assert not result.in_policy
    assert "fare_class" in result.violations[0]


def test_hotel_over_nightly_cap_violates():
    hotel = HotelOption(
        id="3", name="Meridian Suites", location="NYC",
        check_in="2026-09-01", check_out="2026-09-03",
        nightly_rate_cents=40000,
    )
    result = check_rules(hotel, RULES)
    assert not result.in_policy


def test_price_over_threshold_requires_approval_even_if_in_policy():
    flight = FlightOption(
        id="4", airline="Skyward Air", fare_class="economy",
        origin="SFO", destination="JFK", depart_date="2026-09-01",
        price_cents=200000,
    )
    result = check_rules(flight, RULES)
    assert result.in_policy
    assert result.requires_approval
