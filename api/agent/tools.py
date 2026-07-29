from langchain_core.tools import tool

from core.db import get_db
from expense.sync_client import MockExpenseSyncClient
from policy.retrieval import answer_why
from policy.rules import check_rules
from travel.duffel_client import DuffelAPIError, UnknownOfferError, get_duffel_client
from travel.models import FlightOption, HotelOption
from travel.ticketing import issue_ticket

_duffel = get_duffel_client()
_expense = MockExpenseSyncClient()


@tool
def search_travel(kind: str, origin_or_location: str, destination: str = "", date: str = "") -> list[dict]:
    """Search for flights (kind='flight', needs origin_or_location as origin,
    destination, date as depart_date) or hotels (kind='hotel',
    origin_or_location as location, date as check_in, destination as
    check_out — destination must be a check-out date, not an airport/city)."""
    try:
        if kind == "flight":
            options = _duffel.search_flights(origin_or_location, destination, date)
        else:
            options = _duffel.search_hotels(origin_or_location, date, destination)
    except DuffelAPIError as exc:
        # Returned, not raised: LangGraph's default tool-error handler
        # re-raises anything that isn't a ToolInvocationError, which would
        # 500 the whole chat. Handing the message back lets the agent fix a
        # bad airport code or retry instead of failing at the traveler.
        return [{"error": exc.message}]
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
    status = "pending_approval" if check.requires_approval else "booked"

    db = get_db()
    # Ticket BEFORE writing the row: if the supplier call fails we want no
    # booking record at all, rather than a row claiming 'booked' that no
    # airline has ever heard of. A row is recoverable; a phantom ticket isn't.
    if status == "booked":
        try:
            details = issue_ticket(db, trip_id, kind, details)
        except (DuffelAPIError, UnknownOfferError) as exc:
            # Both are expected and recoverable: fares go stale within seconds
            # on aggregator content, and the agent sometimes mangles an offer
            # id. Hand the reason back so it re-searches, rather than raising
            # and 500ing the chat. No row is written, so nothing claims to be
            # booked.
            message = getattr(exc, "message", str(exc))
            return {"status": "unavailable", "error": message, "violations": []}

    # Read the price after ticketing: issue_ticket replaces it with what the
    # supplier actually charged.
    price_cents = details.get("price_cents") or details.get("nightly_rate_cents")

    row = db.table("bookings").insert({
        "trip_id": trip_id,
        "kind": kind,
        "details": details,
        "price_cents": price_cents,
        "status": status,
    }).execute().data[0]

    if status == "booked":
        try:
            _expense.sync_booking(row)
        except Exception:  # noqa: BLE001, S110
            pass  # best-effort: sync failure must never block a completed booking

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
