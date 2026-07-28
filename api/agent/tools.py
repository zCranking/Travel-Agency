from langchain_core.tools import tool

from core.db import get_db
from policy.retrieval import answer_why
from policy.rules import check_rules
from travel.duffel_client import MockDuffelClient
from travel.models import FlightOption, HotelOption

_duffel = MockDuffelClient()


@tool
def search_travel(kind: str, origin_or_location: str, destination: str = "", date: str = "") -> list[dict]:
    """Search for flights (kind='flight', needs origin_or_location as origin,
    destination, date as depart_date) or hotels (kind='hotel',
    origin_or_location as location, date as check_in, destination as
    check_out — destination must be a check-out date, not an airport/city)."""
    if kind == "flight":
        options = _duffel.search_flights(origin_or_location, destination, date)
    else:
        options = _duffel.search_hotels(origin_or_location, date, destination)
    return [o.model_dump() for o in options]


@tool
def check_policy(option: dict, rules: dict, kind: str) -> dict:
    """Check a flight or hotel option against company policy rules."""
    model = FlightOption(**option) if kind == "flight" else HotelOption(**option)
    result = check_rules(model, rules)
    return result.model_dump()


@tool
def why_out_of_policy(question: str, policy_id: str) -> str:
    """Explain, with cited policy language, why something is or isn't in policy."""
    return answer_why(question, policy_id)


@tool
def create_booking(trip_id: str, kind: str, details: dict, rules: dict) -> dict:
    """Book a flight or hotel option for a trip. Lands as 'pending_approval'
    if it violates policy or exceeds the approval threshold, else 'booked'."""
    model = FlightOption(**details) if kind == "flight" else HotelOption(**details)
    check = check_rules(model, rules)
    price_cents = details.get("price_cents") or details.get("nightly_rate_cents")
    status = "pending_approval" if check.requires_approval else "booked"

    db = get_db()
    row = db.table("bookings").insert({
        "trip_id": trip_id,
        "kind": kind,
        "details": details,
        "price_cents": price_cents,
        "status": status,
    }).execute().data[0]

    return {"id": row["id"], "status": status, "violations": check.violations}


@tool
def check_disruptions(trip_id: str) -> list[dict]:
    """Check a trip's flight bookings for disruptions (delays/cancellations).
    Returns only the bookings that are actually affected."""
    db = get_db()
    bookings = (
        db.table("bookings").select("id, kind, details").eq("trip_id", trip_id).execute().data
    )
    disruptions = []
    for booking in bookings:
        if booking["kind"] != "flight":
            continue
        disruption = _duffel.get_disruption(booking["details"])
        if disruption is not None:
            disruptions.append(
                {"booking_id": booking["id"], "type": disruption.type, "message": disruption.message}
            )
    return disruptions
