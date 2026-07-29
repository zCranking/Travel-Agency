from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


@patch("routes.duty_of_care.get_db")
def test_duty_of_care_returns_employee_with_trip_and_risk(mock_get_db):
    db = MagicMock()

    def table(name):
        t = MagicMock()
        if name == "employees":
            t.select.return_value.execute.return_value.data = [
                {"id": "emp-1", "name": "Jordan Lee"}
            ]
        elif name == "trips":
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
                {"id": "trip-1", "thread_id": "trip-1"}
            ]
        elif name == "bookings":
            t.select.return_value.eq.return_value.execute.return_value.data = [
                {
                    "id": "b1",
                    "kind": "flight",
                    "details": {"destination": "JFK"},
                    "status": "booked",
                }
            ]
        elif name == "itineraries":
            # No planner itinerary for this trip, so risk falls back to the
            # placeholder hash.
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        return t

    db.table.side_effect = table
    mock_get_db.return_value = db

    response = client.get("/duty-of-care")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["employee_id"] == "emp-1"
    assert body[0]["name"] == "Jordan Lee"
    assert body[0]["trip"]["trip_id"] == "trip-1"
    assert body[0]["trip"]["destination"] == "JFK"
    assert body[0]["trip"]["risk_level"] in ("low", "medium", "high")
    assert len(body[0]["trip"]["bookings"]) == 1


@patch("routes.duty_of_care.get_db")
def test_duty_of_care_employee_with_no_trip(mock_get_db):
    db = MagicMock()

    def table(name):
        t = MagicMock()
        if name == "employees":
            t.select.return_value.execute.return_value.data = [
                {"id": "emp-2", "name": "Priya Nair"}
            ]
        elif name == "trips":
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        return t

    db.table.side_effect = table
    mock_get_db.return_value = db

    response = client.get("/duty-of-care")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["trip"] is None


def _db(itineraries):
    """One employee, one trip, one flight booking, plus whatever the planner
    left behind on `itineraries`."""
    db = MagicMock()

    def table(name):
        t = MagicMock()
        if name == "employees":
            t.select.return_value.execute.return_value.data = [
                {"id": "emp-1", "name": "Jordan Lee"}
            ]
        elif name == "trips":
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
                {"id": "trip-1", "thread_id": "trip-1"}
            ]
        elif name == "bookings":
            t.select.return_value.eq.return_value.execute.return_value.data = [
                {"id": "b1", "kind": "flight", "details": {"destination": "ORD"},
                 "status": "booked"}
            ]
        elif name == "itineraries":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = itineraries
        return t

    db.table.side_effect = table
    return db


@patch("routes.duty_of_care.get_db")
def test_duty_of_care_prefers_a_real_itinerary_risk_assessment(mock_get_db):
    """The destination hash was always a placeholder. Where the planner has
    produced a real assessment, that wins -- and the response says which it is,
    so the UI never presents a hash as intelligence."""
    mock_get_db.return_value = _db([{"risk": {
        "severity": "high",
        "advisory": "Lands after midnight with a 7am start.",
        "factors": [{"code": "late_arrival", "detail": "Lands at 00:15 local."}],
    }}])

    trip = client.get("/duty-of-care").json()[0]["trip"]

    assert trip["risk_level"] == "high"
    assert trip["risk_source"] == "itinerary"
    assert trip["risk_advisory"]
    assert trip["risk_factors"][0]["code"] == "late_arrival"


@patch("routes.duty_of_care.get_db")
def test_duty_of_care_labels_the_hash_as_a_placeholder(mock_get_db):
    mock_get_db.return_value = _db([])

    trip = client.get("/duty-of-care").json()[0]["trip"]

    assert trip["risk_source"] == "placeholder"
    assert trip["risk_level"] in ("low", "medium", "high")
    assert trip["risk_advisory"] is None
