import httpx
from fastapi import APIRouter, HTTPException

from core.db import get_db
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
    except httpx.HTTPStatusError as exc:
        # ponytail: held fares expire (Duffel offers live ~20-30 min), so an
        # approval that arrives the next morning WILL fail here. Surfacing that
        # honestly beats a 500 or a fake confirmation. Re-searching and
        # repricing at approval time is the real fix — build it when approval
        # latency actually starts costing bookings.
        raise HTTPException(
            status_code=409,
            detail=(
                "Could not ticket this booking — the fare is no longer "
                "available (offers expire shortly after search). Ask the "
                "traveler to search again for a current fare."
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
