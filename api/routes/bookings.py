import httpx
from fastapi import APIRouter, HTTPException

from core.db import get_db
from travel.duffel_client import DuffelAPIError, UnknownOfferError
from travel.ticketing import issue_ticket

router = APIRouter()


@router.get("/trips/{trip_id}/bookings")
def list_bookings(trip_id: str) -> list[dict]:
    db = get_db()
    return db.table("bookings").select("*").eq("trip_id", trip_id).execute().data


@router.post("/bookings/{booking_id}/approve")
def approve_booking(booking_id: str) -> dict:
    db = get_db()
    rows = db.table("bookings").select("*").eq("id", booking_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Booking not found")

    booking = rows[0]
    if booking["status"] == "booked":
        return booking  # idempotent: a second approve must not buy a second ticket

    try:
        details = issue_ticket(db, booking["trip_id"], booking["kind"], booking["details"])
    except (DuffelAPIError, UnknownOfferError) as exc:
        # ponytail: held fares go stale — observed within seconds on
        # aggregator-sourced content, so an approval arriving the next morning
        # will essentially always land here. Surfacing Duffel's own reason
        # beats a 500 or a fake confirmation. Re-searching and repricing at
        # approval time is the real fix — build it when approval latency
        # actually starts costing bookings.
        raise HTTPException(
            status_code=409,
            detail=(
                f"Could not ticket this booking: {getattr(exc, 'message', exc)} "
                "Ask the traveler to search again for a current fare."
            ),
        ) from exc
    except httpx.TimeoutException as exc:
        # Ambiguous: the airline may still ticket. The client already tried to
        # reconcile, so reaching here means no order was found — but say so
        # plainly rather than implying it definitely didn't happen.
        raise HTTPException(
            status_code=504,
            detail=(
                "The airline did not respond in time and no order was found. "
                "Check the Duffel dashboard before approving again."
            ),
        ) from exc

    updated = (
        db.table("bookings")
        .update({"status": "booked", "details": details})
        .eq("id", booking_id)
        .execute()
        .data
    )
    return updated[0]


@router.post("/bookings/{booking_id}/reject")
def reject_booking(booking_id: str) -> dict:
    db = get_db()
    rows = db.table("bookings").update({"status": "rejected"}).eq("id", booking_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Booking not found")
    return rows[0]
