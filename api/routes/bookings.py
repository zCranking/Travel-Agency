from fastapi import APIRouter, HTTPException

from core.db import get_db

router = APIRouter()


@router.get("/trips/{trip_id}/bookings")
def list_bookings(trip_id: str) -> list[dict]:
    db = get_db()
    return db.table("bookings").select("*").eq("trip_id", trip_id).execute().data


@router.post("/bookings/{booking_id}/approve")
def approve_booking(booking_id: str) -> dict:
    db = get_db()
    rows = db.table("bookings").update({"status": "booked"}).eq("id", booking_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Booking not found")
    return rows[0]


@router.post("/bookings/{booking_id}/reject")
def reject_booking(booking_id: str) -> dict:
    db = get_db()
    rows = db.table("bookings").update({"status": "rejected"}).eq("id", booking_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Booking not found")
    return rows[0]
