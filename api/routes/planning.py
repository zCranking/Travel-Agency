"""Constraint-planner endpoints.

Shape of the flow: meetings go in (typed on a form, or drafted by `interpret`
and confirmed), `solve` produces the feasible set, the AI layers rank and
assess it, and the result is persisted *before* it is returned — so selection
later references a plan this server issued rather than one a client handed
back.
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.tools import create_booking, search_travel
from core.db import get_db
from planning.interpret import interpret
from planning.judge import judge
from planning.models import Leg, Meeting, TripIntent
from planning.risk import assess
from planning.solver import solve
from travel.models import FlightOption

router = APIRouter()


class CreateTrip(BaseModel):
    employee_id: str
    origin_city: str | None = None
    budget_cents: int | None = None


class AddMeetings(BaseModel):
    meetings: list[Meeting]


class InterpretRequest(BaseModel):
    text: str


class SelectRequest(BaseModel):
    confirm_reprice: bool = False


def _search_flights(origin: str, destination: str, day: str) -> list[dict]:
    """Thin seam over the existing tool so tests can inject fares without
    reaching for httpx. `.func` unwraps the LangChain @tool decorator."""
    return search_travel.func("flight", origin, destination, day)


def _search_options(origin: str, destination: str, day: str) -> list[FlightOption]:
    return [
        FlightOption(**option)
        for option in _search_flights(origin, destination, day)
        if "error" not in option
    ]


def _trip(db, trip_id: str) -> dict:
    rows = db.table("trips").select("*").eq("id", trip_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Trip not found")
    return rows[0]


def _rules(db, company_id: str) -> dict:
    rows = db.table("policies").select("rules").eq("company_id", company_id).execute().data
    return rows[0]["rules"] if rows else {}


def build_intent(db, trip_id: str) -> TripIntent:
    trip = _trip(db, trip_id)
    meetings = db.table("meetings").select("*").eq("trip_id", trip_id).execute().data
    employees = (
        db.table("employees")
        .select("travel_preferences")
        .eq("id", trip["employee_id"])
        .execute()
        .data
    )
    preferences = (employees[0].get("travel_preferences") if employees else None) or {}
    return TripIntent(
        origin_city=trip.get("origin_city") or "SFO",
        meetings=[Meeting(**m) for m in meetings],
        budget_cents=trip.get("budget_cents"),
        preferences=preferences,
        policy_rules=_rules(db, trip["company_id"]),
    )


@router.post("/trips")
def create_trip(body: CreateTrip) -> dict:
    db = get_db()
    employees = (
        db.table("employees").select("company_id").eq("id", body.employee_id).execute().data
    )
    if not employees:
        raise HTTPException(status_code=404, detail="Employee not found")

    row = db.table("trips").insert({
        # Resolved server-side, never taken from the request — a client-supplied
        # company_id is an IDOR waiting to happen.
        "company_id": employees[0]["company_id"],
        "employee_id": body.employee_id,
        "thread_id": str(uuid.uuid4()),
        "origin_city": body.origin_city,
        "budget_cents": body.budget_cents,
    }).execute().data[0]
    return {"id": row["id"]}


@router.get("/trips/{trip_id}/meetings")
def list_meetings(trip_id: str) -> list[dict]:
    return get_db().table("meetings").select("*").eq("trip_id", trip_id).execute().data


@router.post("/trips/{trip_id}/meetings")
def add_meetings(trip_id: str, body: AddMeetings) -> list[dict]:
    db = get_db()
    _trip(db, trip_id)
    rows = [
        {
            "trip_id": trip_id,
            "title": m.title,
            "city": m.city,
            "mode": m.mode,
            "starts_at": m.starts_at.isoformat(),
            "ends_at": m.ends_at.isoformat(),
            "flexible": m.flexible,
        }
        for m in body.meetings
    ]
    return db.table("meetings").insert(rows).execute().data


@router.delete("/meetings/{meeting_id}")
def delete_meeting(meeting_id: str) -> dict:
    get_db().table("meetings").delete().eq("id", meeting_id).execute()
    return {"ok": True}


@router.post("/trips/{trip_id}/interpret")
def interpret_trip(trip_id: str, body: InterpretRequest) -> dict:
    """Returns a DRAFT. Persists nothing — the traveler confirms it into
    meetings, which is what makes this an accelerant rather than a model
    quietly deciding where someone flies."""
    return interpret(body.text, datetime.now(UTC).date()).model_dump(mode="json")


@router.post("/trips/{trip_id}/plan")
def plan_trip(trip_id: str) -> dict:
    db = get_db()
    intent = build_intent(db, trip_id)
    if not intent.meetings:
        raise HTTPException(
            status_code=400, detail="Add at least one meeting before planning."
        )

    result = solve(intent, _search_options)
    if not result.itineraries:
        return {
            "itineraries": [],
            "binding_constraint": (
                result.binding_constraint.model_dump()
                if result.binding_constraint
                else None
            ),
            "relaxation": result.relaxation,
        }

    # Persist first, so every id the AI layers see is one this server issued.
    stored = db.table("itineraries").insert([
        {
            "trip_id": trip_id,
            "legs": [leg.model_dump(mode="json") for leg in i.legs],
            "total_price_cents": i.total_price_cents,
            "soft_violations": [v.model_dump() for v in i.soft_violations],
        }
        for i in result.itineraries
    ]).execute().data

    for itinerary, row in zip(result.itineraries, stored, strict=True):
        itinerary.id = row["id"]

    rankings = {r.itinerary_id: r for r in judge(result.itineraries, intent)}

    out = []
    for itinerary in result.itineraries:
        ranking = rankings.get(itinerary.id)
        risk = assess(itinerary, intent)
        db.table("itineraries").update({
            "rank": ranking.rank if ranking else None,
            "rationale": ranking.rationale if ranking else None,
            "concerns": ranking.concerns if ranking else [],
            "risk": risk.model_dump(mode="json"),
        }).eq("id", itinerary.id).execute()
        out.append({
            "id": itinerary.id,
            "legs": [leg.model_dump(mode="json") for leg in itinerary.legs],
            "total_price_cents": itinerary.total_price_cents,
            "soft_violations": [v.model_dump() for v in itinerary.soft_violations],
            "rank": ranking.rank if ranking else None,
            "rationale": ranking.rationale if ranking else "",
            "concerns": ranking.concerns if ranking else [],
            "risk": risk.model_dump(mode="json"),
        })

    out.sort(key=lambda i: (i["rank"] is None, i["rank"]))
    return {"itineraries": out, "binding_constraint": None, "relaxation": None}


def _reprice(leg: Leg) -> dict | None:
    """Find today's version of a stored leg.

    Plans ride on schedules, which are stable; offers expire within seconds on
    aggregator content. So the stored offer id is a hint, and this re-search is
    what actually produces something bookable — matched on carrier and
    departure instant, which is what the traveler agreed to.
    """
    for option in _search_flights(leg.origin, leg.destination, leg.depart_at.date().isoformat()):
        if "error" in option:
            return None
        if option.get("airline") != leg.airline or not option.get("depart_at"):
            continue
        if datetime.fromisoformat(option["depart_at"]) == leg.depart_at:
            return option
    return None


@router.post("/itineraries/{itinerary_id}/select")
def select_itinerary(itinerary_id: str, body: SelectRequest) -> dict:
    db = get_db()
    rows = db.table("itineraries").select("*").eq("id", itinerary_id).execute().data
    if not rows:
        # Same rule as the offer cache: selection references something the
        # server produced, or it doesn't happen.
        raise HTTPException(status_code=404, detail="Itinerary not found")

    stored = rows[0]
    priced, unavailable = [], []
    for leg in (Leg(**leg) for leg in stored["legs"]):
        option = _reprice(leg)
        if option is None:
            unavailable.append(f"{leg.origin}->{leg.destination}")
        else:
            priced.append(option)

    if unavailable:
        return {
            "status": "reprice_required",
            "unavailable": unavailable,
            "itinerary": stored,
        }

    total = sum(option["price_cents"] for option in priced)
    if total > stored["total_price_cents"] and not body.confirm_reprice:
        # Any increase, not a percentage band. A decrease books through: nobody
        # needs to consent to paying less.
        return {
            "status": "reprice_required",
            "unavailable": [],
            "itinerary": {**stored, "total_price_cents": total, "legs": priced},
        }

    trip = _trip(db, stored["trip_id"])
    rules = _rules(db, trip["company_id"])
    # Through create_booking, so ticketing still goes via issue_ticket() and
    # keeps every protection the Duffel work established.
    bookings = [
        create_booking.func(stored["trip_id"], "flight", option, rules)
        for option in priced
    ]

    db.table("itineraries").update({"selected": True}).eq("id", itinerary_id).execute()
    status = (
        "booked"
        if all(booking.get("status") == "booked" for booking in bookings)
        else "needs_attention"
    )
    return {"status": status, "bookings": bookings, "total_price_cents": total}
