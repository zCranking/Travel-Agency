"""Turning a policy-cleared selection into an actual ticket.

Two paths mark a booking 'booked': the agent's `create_booking` (in policy,
no approval needed) and a manager's approve endpoint (was pending_approval).
Both route through `issue_ticket` so that 'booked' in the database means the
same thing — a real supplier confirmation — no matter which path produced it.
Before this, `create_booking` wrote 'booked' rows that had never been booked
with anyone.
"""

from travel.duffel_client import get_duffel_client
from travel.models import FlightOption, HotelOption


def get_traveler(db, trip_id: str) -> dict | None:
    """Duffel passenger payload for whoever this trip belongs to. None when
    the profile isn't filled in — the mock client ignores it, and the real
    client raises rather than inventing passenger identity."""
    trips = db.table("trips").select("employee_id").eq("id", trip_id).execute().data
    if not trips:
        return None

    employees = (
        db.table("employees")
        .select("email, traveler_profile")
        .eq("id", trips[0]["employee_id"])
        .execute()
        .data
    )
    if not employees or not employees[0].get("traveler_profile"):
        return None

    return {**employees[0]["traveler_profile"], "email": employees[0]["email"]}


def issue_ticket(db, trip_id: str, kind: str, details: dict) -> dict:
    """Book with the supplier; return `details` plus the confirmation code.

    Raises on supplier failure — a caller must never record a booking as
    'booked' if this did not return.
    """
    option = FlightOption(**details) if kind == "flight" else HotelOption(**details)
    confirmation = get_duffel_client().book(option, get_traveler(db, trip_id))
    return {**details, "confirmation_code": confirmation.confirmation_code}
