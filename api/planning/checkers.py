"""Constraint checkers — the code half of the planner.

Every checker has the same signature, `(itinerary, intent) -> list[Violation]`,
and the two lists at the bottom are the whole extension point. International
support adds `check_visa` and `check_passport_validity` to HARD_CHECKERS and
changes nothing else: the solver, the infeasibility search and the UI all read
these lists rather than knowing what's in them.

Hard means infeasible — the itinerary is not shown. Soft means shown and
flagged. Policy is deliberately soft: an out-of-policy plan routes to the
manager approval path that already exists, and hiding it would make the planner
strictly worse than the chat it replaces.
"""
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from planning.models import Itinerary, TripIntent, Violation
from policy.rules import check_rules
from travel.models import FlightOption

# Airport <-> meeting: deplaning, bags, ground transport, and enough slack that
# a 20-minute taxi delay doesn't cost the meeting. Domestic figures.
GROUND_BUFFER = timedelta(minutes=90)
# At the airport before departure. Combined with GROUND_BUFFER this is the
# ~3.5h a traveler really needs between a meeting ending and a wheels-up.
AIRPORT_LEAD = timedelta(minutes=120)

# Red-eye window, local time at the departure airport.
_RED_EYE_FROM, _RED_EYE_TO = 22, 5

# Open-ended bounds for the occupancy timeline. Deliberately UTC: datetime.max
# with a negative offset overflows on comparison, so the sentinels carry a zero
# offset and let the other side do the arithmetic.
_FOREVER_AGO = datetime.min.replace(tzinfo=UTC)
_FOREVER = datetime.max.replace(tzinfo=UTC)

Checker = Callable[[Itinerary, TripIntent], list[Violation]]


def occupancy(
    itinerary: Itinerary, origin_city: str
) -> list[tuple[str | None, datetime, datetime]]:
    """Where the traveler effectively is, over time.

    `None` marks a transit window — buffered wider than the flight itself,
    because a traveler an hour from landing is not available for an in-person
    meeting. Segments are returned in order and cover the whole timeline; the
    first and last are open-ended.
    """
    if not itinerary.legs:
        return []

    segments: list[tuple[str | None, datetime, datetime]] = []
    here = origin_city
    cursor = _FOREVER_AGO

    for leg in itinerary.legs:
        transit_from = leg.depart_at - AIRPORT_LEAD - GROUND_BUFFER
        transit_to = leg.arrive_at + GROUND_BUFFER
        segments.append((here, cursor, transit_from))
        segments.append((None, transit_from, transit_to))
        here, cursor = leg.destination, transit_to

    segments.append((here, cursor, _FOREVER))
    return segments


def check_presence(itinerary: Itinerary, intent: TripIntent) -> list[Violation]:
    """A binding in-person meeting must fall entirely inside one stay in its
    own city — not straddle a departure, not start while still in transit."""
    segments = occupancy(itinerary, intent.origin_city)
    violations = []
    for meeting in intent.in_person():
        present = any(
            city == meeting.city
            and start <= meeting.starts_at
            and meeting.ends_at <= end
            for city, start, end in segments
        )
        if not present:
            violations.append(
                Violation(
                    kind="presence",
                    severity="hard",
                    meeting_id=meeting.id or None,
                    message=(
                        f"Not on the ground in {meeting.city} for "
                        f"{meeting.title!r} ({meeting.starts_at.isoformat()})."
                    ),
                )
            )
    return violations


def check_no_fly(itinerary: Itinerary, intent: TripIntent) -> list[Violation]:
    """A binding virtual meeting may not overlap airborne time.

    Airborne, not the buffered transit window: a call can be taken from a
    lounge, so only wheels-up to wheels-down counts.
    """
    violations = []
    for meeting in intent.virtual():
        for leg in itinerary.legs:
            if meeting.starts_at < leg.arrive_at and leg.depart_at < meeting.ends_at:
                violations.append(
                    Violation(
                        kind="no_fly",
                        severity="hard",
                        meeting_id=meeting.id or None,
                        message=(
                            f"{meeting.title!r} runs while airborne on "
                            f"{leg.origin}->{leg.destination}."
                        ),
                    )
                )
                break
    return violations


def check_red_eye(itinerary: Itinerary, intent: TripIntent) -> list[Violation]:
    if not intent.preferences.get("avoid_red_eyes"):
        return []
    return [
        Violation(
            kind="red_eye",
            severity="soft",
            message=(
                f"{leg.origin}->{leg.destination} departs "
                f"{leg.depart_at.strftime('%H:%M')} local."
            ),
        )
        for leg in itinerary.legs
        if leg.depart_at.hour >= _RED_EYE_FROM or leg.depart_at.hour < _RED_EYE_TO
    ]


def check_connections(itinerary: Itinerary, intent: TripIntent) -> list[Violation]:
    cap = intent.preferences.get("max_connections")
    if cap is None:
        return []
    return [
        Violation(
            kind="connections",
            severity="soft",
            message=(
                f"{leg.origin}->{leg.destination} has {leg.stops} stop(s), "
                f"more than the {cap} you prefer."
            ),
        )
        for leg in itinerary.legs
        if leg.stops > cap
    ]


def check_budget(itinerary: Itinerary, intent: TripIntent) -> list[Violation]:
    if intent.budget_cents is None or itinerary.total_price_cents <= intent.budget_cents:
        return []
    over = itinerary.total_price_cents - intent.budget_cents
    return [
        Violation(
            kind="budget",
            severity="soft",
            message=f"${over / 100:,.0f} over the trip budget.",
        )
    ]


def check_policy(itinerary: Itinerary, intent: TripIntent) -> list[Violation]:
    """Reuses the existing deterministic rule check, one leg at a time, so the
    planner and the chat agent can never disagree about what's in policy."""
    if not intent.policy_rules:
        return []
    violations = []
    for leg in itinerary.legs:
        option = FlightOption(
            id=leg.offer_id or "",
            airline=leg.airline,
            fare_class=leg.fare_class,
            origin=leg.origin,
            destination=leg.destination,
            depart_date=leg.depart_at.date().isoformat(),
            price_cents=leg.price_cents,
        )
        result = check_rules(option, intent.policy_rules)
        violations.extend(
            Violation(kind="policy", severity="soft", message=message)
            for message in result.violations
        )
    return violations


HARD_CHECKERS: list[Checker] = [check_presence, check_no_fly]
SOFT_CHECKERS: list[Checker] = [
    check_red_eye,
    check_connections,
    check_budget,
    check_policy,
]
