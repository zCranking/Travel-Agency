import hashlib

from fastapi import APIRouter

from core.db import get_db

router = APIRouter()

_RISK_LEVELS = ["low", "medium", "high"]


def _mock_risk_level(destination: str) -> str:
    """Placeholder risk data -- deterministic from the destination string,
    NOT a real risk feed (no Riskline/equivalent integration exists yet).
    The frontend must label this as placeholder, never real intelligence."""
    digest = hashlib.md5(destination.encode()).digest()
    return _RISK_LEVELS[digest[0] % len(_RISK_LEVELS)]


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
        result.append(
            {
                "employee_id": employee["id"],
                "name": employee["name"],
                "trip": {
                    "trip_id": trip["id"],
                    "destination": destination,
                    "risk_level": _mock_risk_level(destination),
                    "bookings": bookings,
                },
            }
        )
    return result
