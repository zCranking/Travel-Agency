from datetime import UTC, datetime, timedelta

from planning.models import Meeting, TripIntent
from planning.solver import city_sequence, solve
from travel.models import FlightOption


def at(day, hour, minute=0):
    return datetime(2026, 9, day, hour, minute, tzinfo=UTC)


def flight(origin, dest, depart, hours=4, price=30000, airline="United", stops=0):
    arrive = depart + timedelta(hours=hours)
    return FlightOption(
        id=f"{origin}{dest}-{depart.isoformat()}",
        airline=airline, fare_class="economy", origin=origin, destination=dest,
        depart_date=depart.date().isoformat(), price_cents=price,
        depart_at=depart.isoformat(), arrive_at=arrive.isoformat(), stops=stops,
    )


def fixture_search(catalog):
    """Build a SearchFn over a fixed catalog. This is why `solve` takes search
    as a parameter -- the whole solver is testable with no network and no
    monkeypatching."""
    def search(origin, destination, date):
        return [
            f for f in catalog
            if f.origin == origin and f.destination == destination
            and f.depart_date == date
        ]
    return search


def meeting(city, start, end, mode="in_person", flexible=False, mid="m1", title="Meeting"):
    return Meeting(id=mid, title=title, city=city, mode=mode,
                   starts_at=start, ends_at=end, flexible=flexible)


# --- city sequence --------------------------------------------------------

def test_city_sequence_is_origin_then_meeting_cities_then_home():
    intent = TripIntent(origin_city="SFO", meetings=[
        meeting("ORD", at(1, 14), at(1, 15), mid="a"),
        meeting("DEN", at(3, 10), at(3, 11), mid="b"),
    ])
    assert city_sequence(intent) == ["SFO", "ORD", "DEN", "SFO"]


def test_city_sequence_collapses_consecutive_meetings_in_one_city():
    intent = TripIntent(origin_city="SFO", meetings=[
        meeting("ORD", at(1, 14), at(1, 15), mid="a"),
        meeting("ORD", at(2, 9), at(2, 10), mid="b"),
    ])
    assert city_sequence(intent) == ["SFO", "ORD", "SFO"]


def test_city_sequence_ignores_virtual_meetings():
    intent = TripIntent(origin_city="SFO", meetings=[
        meeting("ORD", at(1, 14), at(1, 15), mid="a"),
        meeting(None, at(2, 9), at(2, 10), mode="virtual", mid="b"),
    ])
    assert city_sequence(intent) == ["SFO", "ORD", "SFO"]


# --- feasibility ----------------------------------------------------------

def test_solve_returns_only_itineraries_that_make_the_meeting():
    catalog = [
        flight("SFO", "ORD", at(1, 6)),            # lands 10:00 -- works
        flight("SFO", "ORD", at(1, 13)),           # lands 17:00 -- too late
        flight("ORD", "SFO", at(1, 19)),           # home after the meeting
    ]
    intent = TripIntent(origin_city="SFO",
                        meetings=[meeting("ORD", at(1, 14), at(1, 15))])

    result = solve(intent, fixture_search(catalog))

    assert result.binding_constraint is None
    assert len(result.itineraries) == 1
    assert result.itineraries[0].legs[0].depart_at == at(1, 6)


def test_solve_chains_two_cities_in_order():
    catalog = [
        flight("SFO", "ORD", at(1, 6)),
        flight("ORD", "DEN", at(2, 6), hours=3),
        flight("DEN", "SFO", at(2, 20), hours=3),
    ]
    intent = TripIntent(origin_city="SFO", meetings=[
        meeting("ORD", at(1, 14), at(1, 15), mid="a"),
        meeting("DEN", at(2, 14), at(2, 15), mid="b"),
    ])

    result = solve(intent, fixture_search(catalog))

    assert len(result.itineraries) == 1
    assert [(leg.origin, leg.destination) for leg in result.itineraries[0].legs] == [
        ("SFO", "ORD"), ("ORD", "DEN"), ("DEN", "SFO")
    ]


def test_solve_finds_the_night_before_flight_for_an_early_meeting():
    """A 9am meeting is reached by flying the day before, so the solver has to
    search the deadline date *and* the day before it."""
    catalog = [
        flight("SFO", "ORD", at(1, 18)),           # lands 22:00 the night before
        flight("ORD", "SFO", at(2, 16)),
    ]
    intent = TripIntent(origin_city="SFO",
                        meetings=[meeting("ORD", at(2, 9), at(2, 10))])

    result = solve(intent, fixture_search(catalog))

    assert len(result.itineraries) == 1
    assert result.itineraries[0].legs[0].depart_at == at(1, 18)


def test_solve_sorts_by_total_price_and_caps_the_set():
    catalog = [
        flight("SFO", "ORD", at(1, 6), price=50000, airline="A"),
        flight("SFO", "ORD", at(1, 7), price=20000, airline="B"),
        flight("ORD", "SFO", at(1, 19), price=10000),
    ]
    intent = TripIntent(origin_city="SFO",
                        meetings=[meeting("ORD", at(1, 14), at(1, 15))])

    result = solve(intent, fixture_search(catalog))

    totals = [i.total_price_cents for i in result.itineraries]
    assert totals == sorted(totals)
    assert totals[0] == 30000


def test_solve_attaches_soft_violations_without_hiding_the_itinerary():
    catalog = [
        flight("SFO", "ORD", at(1, 6), price=200000),
        flight("ORD", "SFO", at(1, 19), price=10000),
    ]
    intent = TripIntent(
        origin_city="SFO",
        meetings=[meeting("ORD", at(1, 14), at(1, 15))],
        budget_cents=100000,
    )

    result = solve(intent, fixture_search(catalog))

    assert len(result.itineraries) == 1
    assert [v.kind for v in result.itineraries[0].soft_violations] == ["budget"]


def test_solve_respects_a_binding_virtual_meeting():
    """The only workable outbound is airborne during the board call, so there
    is no feasible plan -- and the answer says which constraint did it."""
    catalog = [
        flight("SFO", "ORD", at(1, 6)),            # airborne 06:00-10:00
        flight("ORD", "SFO", at(1, 22)),
    ]
    intent = TripIntent(origin_city="SFO", meetings=[
        meeting("ORD", at(1, 17), at(1, 18), mid="a"),
        meeting(None, at(1, 7), at(1, 8), mode="virtual", mid="v", title="Board call"),
    ])

    result = solve(intent, fixture_search(catalog))

    assert result.itineraries == []
    assert result.binding_constraint.kind == "no_fly"
    assert "Board call" in result.binding_constraint.message


def test_a_flexible_virtual_meeting_unblocks_the_same_search():
    catalog = [
        flight("SFO", "ORD", at(1, 6)),
        flight("ORD", "SFO", at(1, 22)),
    ]
    intent = TripIntent(origin_city="SFO", meetings=[
        meeting("ORD", at(1, 17), at(1, 18), mid="a"),
        meeting(None, at(1, 7), at(1, 8), mode="virtual", mid="v", flexible=True),
    ])

    result = solve(intent, fixture_search(catalog))

    assert len(result.itineraries) == 1
    assert result.binding_constraint is None


def test_solve_names_presence_as_the_binding_constraint_when_timing_is_impossible():
    catalog = [
        flight("SFO", "ORD", at(1, 13)),           # lands 17:00, meeting is at 14:00
        flight("ORD", "SFO", at(1, 22)),
    ]
    intent = TripIntent(origin_city="SFO", meetings=[
        meeting("ORD", at(1, 14), at(1, 15), title="Client pitch")
    ])

    result = solve(intent, fixture_search(catalog))

    assert result.itineraries == []
    assert result.binding_constraint.kind == "presence"
    assert "Client pitch" in result.binding_constraint.message
    assert result.relaxation


def test_solve_reports_no_flights_when_the_route_does_not_exist():
    intent = TripIntent(origin_city="SFO",
                        meetings=[meeting("ORD", at(1, 14), at(1, 15))])

    result = solve(intent, fixture_search([]))

    assert result.itineraries == []
    assert result.binding_constraint.kind == "no_flights"


def test_solve_with_no_in_person_meetings_plans_no_travel():
    """A trip of only virtual meetings needs no flights, and that is a feasible
    answer -- not an error and not an unexplained empty list."""
    intent = TripIntent(origin_city="SFO", meetings=[
        meeting(None, at(1, 9), at(1, 10), mode="virtual")
    ])

    result = solve(intent, fixture_search([]))

    assert result.binding_constraint is None
    assert result.itineraries[0].legs == []


def test_solve_skips_flights_with_no_usable_times():
    """An offer with blank instants is still bookable through chat, but it
    cannot take part in constraint solving -- silently including it would
    produce a plan the solver never actually verified."""
    untimed = FlightOption(
        id="untimed", airline="United", fare_class="economy", origin="SFO",
        destination="ORD", depart_date="2026-09-01", price_cents=10000,
    )
    catalog = [untimed, flight("SFO", "ORD", at(1, 6)), flight("ORD", "SFO", at(1, 19))]
    intent = TripIntent(origin_city="SFO",
                        meetings=[meeting("ORD", at(1, 14), at(1, 15))])

    result = solve(intent, fixture_search(catalog))

    assert result.itineraries
    assert all(leg.offer_id != "untimed"
               for i in result.itineraries for leg in i.legs)


def test_solve_handles_a_dst_boundary():
    """US DST ends 2026-11-01. A trip spanning it must still land before the
    meeting -- naive arithmetic on local times drifts by an hour here."""
    from zoneinfo import ZoneInfo

    chicago = ZoneInfo("America/Chicago")
    depart = datetime(2026, 10, 31, 18, tzinfo=ZoneInfo("America/Los_Angeles"))
    out = FlightOption(
        id="dst", airline="United", fare_class="economy", origin="SFO",
        destination="ORD", depart_date="2026-10-31", price_cents=30000,
        depart_at=depart.isoformat(),
        arrive_at=(depart + timedelta(hours=4)).isoformat(),
    )
    home = FlightOption(
        id="dst-home", airline="United", fare_class="economy", origin="ORD",
        destination="SFO", depart_date="2026-11-01", price_cents=30000,
        depart_at=datetime(2026, 11, 1, 18, tzinfo=chicago).isoformat(),
        arrive_at=datetime(2026, 11, 1, 21, tzinfo=chicago).isoformat(),
    )
    intent = TripIntent(origin_city="SFO", meetings=[
        meeting("ORD", datetime(2026, 11, 1, 9, tzinfo=chicago),
                datetime(2026, 11, 1, 10, tzinfo=chicago))
    ])

    result = solve(intent, fixture_search([out, home]))

    assert len(result.itineraries) == 1
