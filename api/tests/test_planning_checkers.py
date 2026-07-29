from datetime import UTC, datetime

from planning.checkers import (
    check_budget,
    check_connections,
    check_no_fly,
    check_policy,
    check_presence,
    check_red_eye,
)
from planning.models import Itinerary, Leg, Meeting, TripIntent


def at(day, hour, minute=0):
    return datetime(2026, 9, day, hour, minute, tzinfo=UTC)


def leg(origin, dest, depart, arrive, price=30000, stops=0, fare="economy"):
    return Leg(
        origin=origin, destination=dest, depart_at=depart, arrive_at=arrive,
        airline="United", fare_class=fare, price_cents=price, stops=stops,
    )


def meeting(city, start, end, mode="in_person", flexible=False, mid="m1", title="Meeting"):
    return Meeting(
        id=mid, title=title, city=city, mode=mode,
        starts_at=start, ends_at=end, flexible=flexible,
    )


def intent(meetings, **kw):
    return TripIntent(origin_city="SFO", meetings=meetings, **kw)


# --- presence -------------------------------------------------------------

def test_presence_accepts_a_comfortable_arrival():
    itinerary = Itinerary.from_legs([leg("SFO", "ORD", at(1, 6), at(1, 11))])
    assert check_presence(itinerary, intent([meeting("ORD", at(1, 14), at(1, 15))])) == []


def test_presence_rejects_landing_twenty_minutes_before_the_meeting():
    """Landing is not being there -- deplaning, bags and a cab are real, and
    GROUND_BUFFER is what encodes that."""
    itinerary = Itinerary.from_legs([leg("SFO", "ORD", at(1, 9), at(1, 13, 40))])
    violations = check_presence(itinerary, intent([meeting("ORD", at(1, 14), at(1, 15))]))
    assert [v.kind for v in violations] == ["presence"]
    assert violations[0].meeting_id == "m1"


def test_presence_rejects_leaving_before_the_meeting_ends():
    itinerary = Itinerary.from_legs([
        leg("SFO", "ORD", at(1, 6), at(1, 11)),
        leg("ORD", "SFO", at(1, 14, 30), at(1, 18)),
    ])
    trip = intent([meeting("ORD", at(1, 14), at(1, 16))])
    assert [v.kind for v in check_presence(itinerary, trip)] == ["presence"]


def test_presence_rejects_being_in_the_wrong_city_entirely():
    itinerary = Itinerary.from_legs([leg("SFO", "DEN", at(1, 6), at(1, 10))])
    trip = intent([meeting("ORD", at(1, 14), at(1, 15))])
    assert [v.kind for v in check_presence(itinerary, trip)] == ["presence"]


def test_presence_ignores_a_flexible_meeting():
    itinerary = Itinerary.from_legs([leg("SFO", "DEN", at(1, 6), at(1, 10))])
    trip = intent([meeting("ORD", at(1, 14), at(1, 15), flexible=True)])
    assert check_presence(itinerary, trip) == []


def test_presence_handles_meetings_across_timezones():
    """2pm Chicago is 12pm Denver. A solver comparing wall clocks would call
    this feasible; comparing instants shows the traveler is still airborne."""
    chicago_2pm = datetime(2026, 9, 1, 19, tzinfo=UTC)     # 14:00 CDT
    itinerary = Itinerary.from_legs([
        leg("SFO", "ORD", datetime(2026, 9, 1, 16, tzinfo=UTC),
            datetime(2026, 9, 1, 20, tzinfo=UTC))          # lands 15:00 CDT
    ])
    trip = intent([meeting("ORD", chicago_2pm, datetime(2026, 9, 1, 20, 30, tzinfo=UTC))])
    assert [v.kind for v in check_presence(itinerary, trip)] == ["presence"]


# --- no-fly ---------------------------------------------------------------

def test_no_fly_rejects_a_binding_virtual_meeting_taken_in_the_air():
    itinerary = Itinerary.from_legs([leg("SFO", "ORD", at(1, 9), at(1, 14))])
    trip = intent([meeting(None, at(1, 10), at(1, 11), mode="virtual", mid="v1")])
    violations = check_no_fly(itinerary, trip)
    assert [v.kind for v in violations] == ["no_fly"]
    assert violations[0].meeting_id == "v1"


def test_no_fly_allows_a_call_on_the_ground_between_flights():
    """The buffered transit window blocks presence, not connectivity -- you can
    take a call in a lounge. Only genuinely airborne time counts."""
    itinerary = Itinerary.from_legs([leg("SFO", "ORD", at(1, 9), at(1, 14))])
    trip = intent([meeting(None, at(1, 15), at(1, 16), mode="virtual")])
    assert check_no_fly(itinerary, trip) == []


def test_no_fly_relaxes_for_a_flexible_virtual_meeting():
    itinerary = Itinerary.from_legs([leg("SFO", "ORD", at(1, 9), at(1, 14))])
    trip = intent([meeting(None, at(1, 10), at(1, 11), mode="virtual", flexible=True)])
    assert check_no_fly(itinerary, trip) == []


# --- soft checkers --------------------------------------------------------

def test_red_eye_flags_a_late_night_departure_when_the_traveler_avoids_them():
    itinerary = Itinerary.from_legs([leg("SFO", "ORD", at(1, 23), at(2, 5))])
    trip = intent([], preferences={"avoid_red_eyes": True})
    assert [v.kind for v in check_red_eye(itinerary, trip)] == ["red_eye"]


def test_red_eye_is_silent_when_the_traveler_does_not_care():
    itinerary = Itinerary.from_legs([leg("SFO", "ORD", at(1, 23), at(2, 5))])
    assert check_red_eye(itinerary, intent([])) == []


def test_connections_flags_more_stops_than_the_traveler_accepts():
    itinerary = Itinerary.from_legs([leg("SFO", "ORD", at(1, 6), at(1, 16), stops=2)])
    trip = intent([], preferences={"max_connections": 1})
    assert [v.kind for v in check_connections(itinerary, trip)] == ["connections"]


def test_budget_flags_going_over_and_stays_quiet_under():
    itinerary = Itinerary.from_legs([leg("SFO", "ORD", at(1, 6), at(1, 11), price=90000)])
    assert [v.kind for v in check_budget(itinerary, intent([], budget_cents=50000))] == ["budget"]
    assert check_budget(itinerary, intent([], budget_cents=100000)) == []
    assert check_budget(itinerary, intent([])) == []      # no budget set


def test_policy_is_soft_so_an_out_of_policy_plan_is_shown_and_flagged():
    """Hiding it would make the planner less useful than the chat it replaces
    -- the manager approval path already exists for exactly this."""
    itinerary = Itinerary.from_legs([
        leg("SFO", "ORD", at(1, 6), at(1, 11), fare="business")
    ])
    trip = intent([], policy_rules={
        "max_fare_class": "economy",
        "max_hotel_nightly_rate_cents": 25000,
        "approval_threshold_cents": 150000,
    })
    violations = check_policy(itinerary, trip)
    assert [v.severity for v in violations] == ["soft"]
    assert "business" in violations[0].message


def test_policy_is_silent_with_no_rules_configured():
    itinerary = Itinerary.from_legs([leg("SFO", "ORD", at(1, 6), at(1, 11))])
    assert check_policy(itinerary, intent([])) == []
