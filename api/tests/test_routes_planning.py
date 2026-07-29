from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from main import app
from planning.models import (
    Itinerary,
    Leg,
    PlanResult,
    Ranking,
    RiskAssessment,
    Violation,
)

client = TestClient(app)

TRIP = {
    "id": "trip-1", "employee_id": "emp-1", "company_id": "co-1",
    "origin_city": "SFO", "budget_cents": 200000,
}
MEETING = {
    "id": "m1", "trip_id": "trip-1", "title": "Client pitch", "city": "ORD",
    "mode": "in_person", "flexible": False,
    "starts_at": "2026-09-01T14:00:00-05:00",
    "ends_at": "2026-09-01T15:00:00-05:00",
}
RULES = {
    "max_fare_class": "economy",
    "max_hotel_nightly_rate_cents": 25000,
    "approval_threshold_cents": 150000,
}
DEPART = datetime(2026, 9, 1, 6, tzinfo=UTC)


def _leg(price=30000):
    return Leg(
        origin="SFO", destination="ORD", depart_at=DEPART,
        arrive_at=DEPART + timedelta(hours=4), airline="United",
        fare_class="economy", price_cents=price, offer_id="off_1",
    )


def _fresh(price):
    """What a re-search returns for the stored leg -- same carrier, same
    departure instant, a new offer id."""
    return {
        "id": "off_fresh", "airline": "United", "fare_class": "economy",
        "origin": "SFO", "destination": "ORD", "depart_date": "2026-09-01",
        "price_cents": price, "depart_at": DEPART.isoformat(),
        "arrive_at": (DEPART + timedelta(hours=4)).isoformat(), "stops": 0,
    }


def _stored_itinerary(price=30000):
    return {
        "id": "it-1", "trip_id": "trip-1",
        "legs": [_leg(price).model_dump(mode="json")],
        "total_price_cents": price,
    }


def _db(**tables):
    """Minimal Supabase-client double. `tables` maps table name -> the rows any
    select on it returns."""
    db = MagicMock()
    handles = {}

    def table(name):
        if name in handles:
            return handles[name]
        handle = MagicMock()
        rows = tables.get(name, [])
        handle.select.return_value.eq.return_value.execute.return_value.data = rows
        handle.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = rows
        handle.insert.return_value.execute.return_value.data = rows or [{"id": "new-1"}]
        handle.update.return_value.eq.return_value.execute.return_value.data = rows
        handle.delete.return_value.eq.return_value.execute.return_value.data = rows
        handles[name] = handle
        return handle

    db.table.side_effect = table
    return db


# --- trips / meetings -----------------------------------------------------

@patch("routes.planning.get_db")
def test_create_trip_resolves_the_company_server_side(mock_get_db):
    """The client sends an employee id; company_id is never taken from the
    request -- that would be an IDOR waiting to happen."""
    db = _db(employees=[{"company_id": "co-1"}], trips=[{"id": "trip-9"}])
    mock_get_db.return_value = db

    response = client.post("/trips", json={"employee_id": "emp-1", "origin_city": "SFO"})

    assert response.status_code == 200
    assert response.json()["id"] == "trip-9"
    inserted = db.table("trips").insert.call_args[0][0]
    assert inserted["company_id"] == "co-1"
    assert inserted["thread_id"]


@patch("routes.planning.get_db")
def test_create_trip_404s_for_an_unknown_employee(mock_get_db):
    mock_get_db.return_value = _db(employees=[])
    assert client.post("/trips", json={"employee_id": "nope"}).status_code == 404


@patch("routes.planning.get_db")
def test_add_meetings_rejects_an_in_person_meeting_with_no_city(mock_get_db):
    """Validated at the boundary, mirroring the DB check constraint, so the
    error is readable instead of a 500 out of Postgres."""
    mock_get_db.return_value = _db(trips=[TRIP])

    response = client.post("/trips/trip-1/meetings", json={"meetings": [{
        "title": "Pitch", "mode": "in_person",
        "starts_at": "2026-09-01T14:00:00-05:00",
        "ends_at": "2026-09-01T15:00:00-05:00",
    }]})

    assert response.status_code == 422


@patch("routes.planning.get_db")
def test_add_meetings_rejects_a_naive_datetime(mock_get_db):
    mock_get_db.return_value = _db(trips=[TRIP])

    response = client.post("/trips/trip-1/meetings", json={"meetings": [{
        "title": "Pitch", "city": "ORD", "mode": "in_person",
        "starts_at": "2026-09-01T14:00:00",     # no offset
        "ends_at": "2026-09-01T15:00:00",
    }]})

    assert response.status_code == 422


# --- plan -----------------------------------------------------------------

@patch("routes.planning.assess")
@patch("routes.planning.judge")
@patch("routes.planning.solve")
@patch("routes.planning.get_db")
def test_plan_persists_itineraries_and_returns_them_ranked(
    mock_get_db, mock_solve, mock_judge, mock_assess
):
    mock_get_db.return_value = _db(
        trips=[TRIP], meetings=[MEETING], employees=[{"travel_preferences": {}}],
        policies=[{"id": "pol-1", "rules": RULES}],
        itineraries=[{"id": "it-1"}],
    )
    mock_solve.return_value = PlanResult(itineraries=[Itinerary.from_legs([_leg()])])
    mock_judge.return_value = [Ranking(itinerary_id="it-1", rank=1, rationale="Cheapest")]
    mock_assess.return_value = RiskAssessment(severity="low", advisory="Fine")

    body = client.post("/trips/trip-1/plan").json()

    assert len(body["itineraries"]) == 1
    assert body["itineraries"][0]["rationale"] == "Cheapest"
    assert body["itineraries"][0]["risk"]["severity"] == "low"
    # the id comes from the persisted row, never from the model
    assert body["itineraries"][0]["id"] == "it-1"


@patch("routes.planning.solve")
@patch("routes.planning.get_db")
def test_plan_returns_the_binding_constraint_instead_of_an_empty_list(
    mock_get_db, mock_solve
):
    """'No results' is the one answer a traveler can do nothing with."""
    mock_get_db.return_value = _db(
        trips=[TRIP], meetings=[MEETING], employees=[{"travel_preferences": {}}],
        policies=[{"id": "pol-1", "rules": RULES}],
    )
    mock_solve.return_value = PlanResult(
        binding_constraint=Violation(
            kind="presence", severity="hard", message="No flight arrives early enough.",
        ),
        relaxation="Move the meeting later.",
    )

    body = client.post("/trips/trip-1/plan").json()

    assert body["itineraries"] == []
    assert body["binding_constraint"]["kind"] == "presence"
    assert body["relaxation"]


@patch("routes.planning.get_db")
def test_plan_400s_when_the_trip_has_no_meetings(mock_get_db):
    mock_get_db.return_value = _db(
        trips=[TRIP], meetings=[], employees=[{"travel_preferences": {}}],
        policies=[{"id": "pol-1", "rules": RULES}],
    )
    assert client.post("/trips/trip-1/plan").status_code == 400


# --- select / reprice -----------------------------------------------------

@patch("routes.planning._search_flights")
@patch("routes.planning.get_db")
def test_select_asks_for_confirmation_when_the_price_went_up(mock_get_db, mock_search):
    """Any increase, not a percentage band: silently charging more than the
    displayed price is not a thing to tune."""
    mock_get_db.return_value = _db(
        itineraries=[_stored_itinerary()], trips=[TRIP],
        policies=[{"id": "pol-1", "rules": RULES}],
    )
    mock_search.return_value = [_fresh(41000)]

    body = client.post("/itineraries/it-1/select", json={}).json()

    assert body["status"] == "reprice_required"
    assert body["itinerary"]["total_price_cents"] == 41000


@patch("routes.planning.create_booking")
@patch("routes.planning._search_flights")
@patch("routes.planning.get_db")
def test_select_books_a_confirmed_increase(mock_get_db, mock_search, mock_create_booking):
    mock_get_db.return_value = _db(
        itineraries=[_stored_itinerary()], trips=[TRIP],
        policies=[{"id": "pol-1", "rules": RULES}],
    )
    mock_search.return_value = [_fresh(41000)]
    mock_create_booking.func.return_value = {"id": "bk-1", "status": "booked", "violations": []}

    body = client.post("/itineraries/it-1/select", json={"confirm_reprice": True}).json()

    assert body["status"] == "booked"


@patch("routes.planning.create_booking")
@patch("routes.planning._search_flights")
@patch("routes.planning.get_db")
def test_select_books_a_price_drop_without_asking(mock_get_db, mock_search, mock_create_booking):
    """Nobody needs to consent to paying less."""
    mock_get_db.return_value = _db(
        itineraries=[_stored_itinerary()], trips=[TRIP],
        policies=[{"id": "pol-1", "rules": RULES}],
    )
    mock_search.return_value = [_fresh(21000)]
    mock_create_booking.func.return_value = {"id": "bk-1", "status": "booked", "violations": []}

    body = client.post("/itineraries/it-1/select", json={}).json()

    assert body["status"] == "booked"
    assert body["total_price_cents"] == 21000


@patch("routes.planning.create_booking")
@patch("routes.planning._search_flights")
@patch("routes.planning.get_db")
def test_select_books_from_the_fresh_offer_not_the_stored_one(
    mock_get_db, mock_search, mock_create_booking
):
    """The stored offer id is a hint -- Duffel offers go stale in seconds, so
    what gets booked has to be what the re-search just returned."""
    mock_get_db.return_value = _db(
        itineraries=[_stored_itinerary()], trips=[TRIP],
        policies=[{"id": "pol-1", "rules": RULES}],
    )
    mock_search.return_value = [_fresh(30000)]
    mock_create_booking.func.return_value = {"id": "bk-1", "status": "booked", "violations": []}

    body = client.post("/itineraries/it-1/select", json={}).json()

    assert body["status"] == "booked"
    booked_details = mock_create_booking.func.call_args[0][2]
    assert booked_details["id"] == "off_fresh"


@patch("routes.planning._search_flights")
@patch("routes.planning.get_db")
def test_select_refuses_when_a_leg_no_longer_exists(mock_get_db, mock_search):
    mock_get_db.return_value = _db(
        itineraries=[_stored_itinerary()], trips=[TRIP],
        policies=[{"id": "pol-1", "rules": RULES}],
    )
    mock_search.return_value = []

    body = client.post("/itineraries/it-1/select", json={}).json()

    assert body["status"] == "reprice_required"
    assert body["unavailable"] == ["SFO->ORD"]


@patch("routes.planning.create_booking")
@patch("routes.planning._search_flights")
@patch("routes.planning.get_db")
def test_select_reports_needs_attention_when_a_leg_lands_in_approval(
    mock_get_db, mock_search, mock_create_booking
):
    mock_get_db.return_value = _db(
        itineraries=[_stored_itinerary()], trips=[TRIP],
        policies=[{"id": "pol-1", "rules": RULES}],
    )
    mock_search.return_value = [_fresh(30000)]
    mock_create_booking.func.return_value = {
        "id": "bk-1", "status": "pending_approval", "violations": ["over threshold"],
    }

    body = client.post("/itineraries/it-1/select", json={}).json()

    assert body["status"] == "needs_attention"


@patch("routes.planning.get_db")
def test_select_404s_for_an_itinerary_we_never_issued(mock_get_db):
    """Same rule as the offer cache: selection references something the server
    produced, or it doesn't happen."""
    mock_get_db.return_value = _db(itineraries=[])
    assert client.post("/itineraries/made-up/select", json={}).status_code == 404
