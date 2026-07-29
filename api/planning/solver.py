"""The solver — the code half of the planner, and a pure function.

`search` is injected rather than imported so the whole thing is table-testable
against fixtures with no network and no monkeypatching of module globals. That
isolation is the point: this is where correctness lives.

It enumerates itineraries satisfying every hard constraint, ranks them by
price, and attaches soft violations. When nothing is feasible it does not
return an empty list — an empty list is the one answer a traveler can do
nothing with. It returns the constraint that is actually blocking.
"""
from collections.abc import Callable, Iterator
from datetime import date, datetime, timedelta
from itertools import product

from planning.checkers import (
    AIRPORT_LEAD,
    GROUND_BUFFER,
    HARD_CHECKERS,
    SOFT_CHECKERS,
    Checker,
    check_no_fly,
)
from planning.models import Itinerary, Leg, PlanResult, TripIntent, Violation
from travel.models import FlightOption

SearchFn = Callable[[str, str, str], list[FlightOption]]

# The judge reasons over a handful, not a combinatorial explosion, and every
# extra option is tokens spent making a worse-ranked plan legible.
MAX_ITINERARIES = 5

Stays = dict[str, tuple[datetime, datetime]]


def city_sequence(intent: TripIntent) -> list[str]:
    """origin -> binding in-person cities in time order -> origin.

    Consecutive duplicates collapse: two meetings in Chicago on consecutive
    days is one stay, not a flight out and back.
    """
    cities = [intent.origin_city]
    for meeting in sorted(intent.in_person(), key=lambda m: m.starts_at):
        if meeting.city != cities[-1]:
            cities.append(meeting.city)
    if len(cities) == 1:
        return cities
    return [*cities, intent.origin_city]


def _stays(intent: TripIntent) -> Stays:
    """city -> (be on the ground by, may leave after).

    ponytail: keyed by city, so a trip that visits one city twice merges both
    visits into a single window. Fine for the two-or-three-meeting trips this
    slice targets; key by (city, hop index) when a real revisit shows up.
    """
    windows: Stays = {}
    for meeting in intent.in_person():
        be_there_by = meeting.starts_at - GROUND_BUFFER
        may_leave = meeting.ends_at + GROUND_BUFFER + AIRPORT_LEAD
        existing = windows.get(meeting.city)
        windows[meeting.city] = (
            (min(existing[0], be_there_by), max(existing[1], may_leave))
            if existing
            else (be_there_by, may_leave)
        )
    return windows


def _to_leg(option: FlightOption) -> Leg | None:
    """A flight with no readable schedule cannot be constraint-solved.
    Dropping it beats including a leg whose timing was never verified."""
    if not option.depart_at or not option.arrive_at:
        return None
    try:
        depart = datetime.fromisoformat(option.depart_at)
        arrive = datetime.fromisoformat(option.arrive_at)
    except ValueError:
        return None
    if depart.tzinfo is None or arrive.tzinfo is None or arrive <= depart:
        return None
    return Leg(
        origin=option.origin,
        destination=option.destination,
        depart_at=depart,
        arrive_at=arrive,
        airline=option.airline,
        fare_class=option.fare_class,
        price_cents=option.price_cents,
        stops=option.stops,
        offer_id=option.id,
    )


def _candidate_dates(anchor: datetime, before: bool) -> list[str]:
    """The deadline's own date plus the day before it — an early meeting is
    usually reached by flying the night before. For the return hop the extra
    day goes forwards instead."""
    day: date = anchor.date()
    other = day - timedelta(days=1) if before else day + timedelta(days=1)
    return [d.isoformat() for d in sorted({day, other})]


def _hop_candidates(
    origin: str, destination: str, search: SearchFn, anchor: datetime, before: bool
) -> list[Leg]:
    legs: list[Leg] = []
    for day in _candidate_dates(anchor, before):
        for option in search(origin, destination, day):
            leg = _to_leg(option)
            if leg is not None:
                legs.append(leg)
    return legs


def _combinations(hops: list[list[Leg]], stays: Stays) -> Iterator[list[Leg]]:
    """Cartesian product across hops, pruned as it goes.

    Two gates. Ordering — you cannot depart before you land — is physics and
    always applies. The stay windows are the presence constraint, and pass
    `stays={}` to drop them: that is how the infeasibility search asks "would
    this work if the meeting times weren't in the way?"
    """
    for combination in product(*hops):
        ok = True
        previous: Leg | None = None
        for leg in combination:
            if previous is not None and leg.depart_at < previous.arrive_at:
                ok = False
                break
            arriving_at = stays.get(leg.destination)
            if arriving_at is not None and leg.arrive_at > arriving_at[0]:
                ok = False
                break
            departing_from = stays.get(leg.origin)
            if departing_from is not None and leg.depart_at < departing_from[1]:
                ok = False
                break
            previous = leg
        if ok:
            yield list(combination)


def _feasible(
    intent: TripIntent,
    search: SearchFn,
    hard: list[Checker],
    enforce_windows: bool = True,
) -> list[Itinerary]:
    cities = city_sequence(intent)
    if len(cities) == 1:
        return [Itinerary.from_legs([])]     # virtual-only trip: no travel needed

    stays = _stays(intent)
    hops: list[list[Leg]] = []
    for i in range(len(cities) - 1):
        origin, destination = cities[i], cities[i + 1]
        returning = i == len(cities) - 2
        anchor = stays[origin][1] if returning else stays[destination][0]
        candidates = _hop_candidates(origin, destination, search, anchor, not returning)
        if not candidates:
            return []
        hops.append(candidates)

    itineraries = []
    for legs in _combinations(hops, stays if enforce_windows else {}):
        itinerary = Itinerary.from_legs(legs)
        if any(checker(itinerary, intent) for checker in hard):
            continue
        itineraries.append(itinerary)

    itineraries.sort(key=lambda i: i.total_price_cents)
    return itineraries[:MAX_ITINERARIES]


def _binding_constraint(intent: TripIntent, search: SearchFn) -> PlanResult:
    """Why is nothing feasible? Relax one hard constraint at a time; the first
    relaxation that yields results names the constraint actually blocking.

    Cheap at two or three meetings, and it is exactly the answer the traveler
    needs — "move the Denver meeting to 11am" beats "no results".
    """
    without_no_fly = [c for c in HARD_CHECKERS if c is not check_no_fly]
    if flyable := _feasible(intent, search, without_no_fly):
        blocked = next(
            (
                violation
                for itinerary in flyable
                for violation in check_no_fly(itinerary, intent)
            ),
            None,
        )
        return PlanResult(
            binding_constraint=blocked
            or Violation(
                kind="no_fly",
                severity="hard",
                message="A virtual meeting overlaps every workable flight.",
            ),
            relaxation="Mark that call flexible, or move it outside the flight window.",
        )

    # Windows off as well as checkers: the meeting times are baked into the
    # hop pruning, so leaving them on would report "no flights" for a route
    # that has plenty, just none early enough.
    if _feasible(intent, search, [], enforce_windows=False):
        first = min(intent.in_person(), key=lambda m: m.starts_at, default=None)
        return PlanResult(
            binding_constraint=Violation(
                kind="presence",
                severity="hard",
                meeting_id=(first.id or None) if first else None,
                message=(
                    f"No flight arrives early enough to make {first.title!r} "
                    f"in {first.city}."
                    if first
                    else "The meeting times cannot be reached by any flight."
                ),
            ),
            relaxation=(
                "Move the earliest meeting later, allow an overnight the day "
                "before, or attend that one remotely."
            ),
        )

    return PlanResult(
        binding_constraint=Violation(
            kind="no_flights",
            severity="hard",
            message="No flights were returned for one or more legs of this route.",
        ),
        relaxation="Try nearby airports or different dates.",
    )


def solve(intent: TripIntent, search: SearchFn) -> PlanResult:
    itineraries = _feasible(intent, search, HARD_CHECKERS)
    if not itineraries:
        return _binding_constraint(intent, search)

    for itinerary in itineraries:
        itinerary.soft_violations = [
            violation
            for checker in SOFT_CHECKERS
            for violation in checker(itinerary, intent)
        ]
    return PlanResult(itineraries=itineraries)
