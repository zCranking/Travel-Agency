import hashlib

from fastapi import APIRouter

from core.db import get_db

router = APIRouter()

_RISK_LEVELS = ["low", "medium", "high"]


def _mock_risk_level(destination: str) -> str:
    """Placeholder risk data -- deterministic from the destination string, NOT
    a real risk feed. Now only the fallback for trips the planner has not
    produced an itinerary for; where a real itinerary-derived assessment
    exists, that wins. The response says which source it came from, and the
    frontend must never present this one as intelligence."""
    digest = hashlib.md5(destination.encode()).digest()
    return _RISK_LEVELS[digest[0] % len(_RISK_LEVELS)]


def _selected_risk(db, trip_id: str) -> dict | None:
    """The risk assessment attached to the itinerary the traveler actually
    chose, if the planner produced one."""
    rows = (
        db.table("itineraries")
        .select("risk")
        .eq("trip_id", trip_id)
        .eq("selected", True)
        .execute()
        .data
    )
    return rows[0]["risk"] if rows and rows[0].get("risk") else None


@router.get("/duty-of-care")
def duty_of_care() -> list[dict]:
    db = get_db()
    employees = db.table("employees").select("id, name").execute().data

    result = []
    for employee in employees:
        trips = (
            db.table("trips")
            .select("id, thread_id")
            .eq("employee_id", employee["id"])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
            .data
        )
        if not trips:
            result.append({"employee_id": employee["id"], "name": employee["name"], "trip": None})
            continue

        trip = trips[0]
        bookings = (
            db.table("bookings").select("id, kind, details, status").eq("trip_id", trip["id"]).execute().data
        )
        destination = next(
            (b["details"].get("destination") for b in bookings if b["kind"] == "flight"),
            "Unknown",
        )
        assessment = _selected_risk(db, trip["id"])
        result.append(
            {
                "employee_id": employee["id"],
                "name": employee["name"],
                "trip": {
                    "trip_id": trip["id"],
                    "destination": destination,
                    "risk_level": (
                        assessment["severity"] if assessment
                        else _mock_risk_level(destination)
                    ),
                    # The destination hash was never intelligence. Saying which
                    # source this came from is what stops the UI presenting it
                    # as one.
                    "risk_source": "itinerary" if assessment else "placeholder",
                    "risk_advisory": assessment.get("advisory") if assessment else None,
                    "risk_factors": assessment.get("factors", []) if assessment else [],
                    "bookings": bookings,
                },
            }
        )
    return result
