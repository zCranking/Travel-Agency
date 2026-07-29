from datetime import UTC, datetime, timedelta

import pytest

from planning.models import Itinerary, Leg, Meeting, TripIntent


def _leg(price=10000, **kw):
    base = {
        "origin": "SFO", "destination": "ORD",
        "depart_at": datetime(2026, 9, 1, 7, tzinfo=UTC),
        "arrive_at": datetime(2026, 9, 1, 13, tzinfo=UTC),
        "airline": "United", "fare_class": "economy", "price_cents": price,
    }
    return Leg(**{**base, **kw})


def test_itinerary_totals_its_legs():
    assert Itinerary.from_legs([_leg(10000), _leg(15000)]).total_price_cents == 25000


def test_meeting_rejects_a_naive_datetime():
    """Every comparison in the solver is instant-to-instant. A naive datetime
    would raise deep inside the solver instead of at the boundary."""
    with pytest.raises(ValueError, match="timezone-aware"):
        Meeting(
            title="Pitch", city="ORD", mode="in_person",
            starts_at=datetime(2026, 9, 1, 14),  # noqa: DTZ001 -- naive on purpose
            ends_at=datetime(2026, 9, 1, 15, tzinfo=UTC),
        )


def test_meeting_rejects_a_backwards_interval():
    with pytest.raises(ValueError, match="ends_at"):
        Meeting(
            title="Pitch", city="ORD", mode="in_person",
            starts_at=datetime(2026, 9, 1, 15, tzinfo=UTC),
            ends_at=datetime(2026, 9, 1, 14, tzinfo=UTC),
        )


def test_in_person_meeting_requires_a_city():
    """Mirrors the DB check constraint. A guessed city books a real ticket to
    the wrong place, so this fails rather than defaulting."""
    with pytest.raises(ValueError, match="city"):
        Meeting(
            title="Pitch", mode="in_person",
            starts_at=datetime(2026, 9, 1, 14, tzinfo=UTC),
            ends_at=datetime(2026, 9, 1, 15, tzinfo=UTC),
        )


def test_virtual_meeting_needs_no_city():
    meeting = Meeting(
        title="Board call", mode="virtual",
        starts_at=datetime(2026, 9, 2, 17, tzinfo=UTC),
        ends_at=datetime(2026, 9, 2, 18, tzinfo=UTC),
    )
    assert meeting.city is None
    assert meeting.flexible is False  # binding unless said otherwise


def test_leg_rejects_arriving_before_it_departs():
    with pytest.raises(ValueError, match="arrive_at"):
        _leg(arrive_at=datetime(2026, 9, 1, 6, tzinfo=UTC))


def test_trip_intent_defaults_are_permissive_but_present():
    intent = TripIntent(origin_city="SFO", meetings=[])
    assert intent.budget_cents is None
    assert intent.preferences == {}
    assert intent.policy_rules == {}
    assert intent.binding_meetings() == []


def test_binding_meetings_excludes_flexible_ones():
    hard = Meeting(
        title="Pitch", city="ORD", mode="in_person",
        starts_at=datetime(2026, 9, 1, 14, tzinfo=UTC),
        ends_at=datetime(2026, 9, 1, 15, tzinfo=UTC),
    )
    soft = hard.model_copy(update={"title": "Optional sync", "flexible": True})
    intent = TripIntent(origin_city="SFO", meetings=[hard, soft])
    assert [m.title for m in intent.binding_meetings()] == ["Pitch"]


def test_leg_duration():
    assert _leg().duration == timedelta(hours=6)
