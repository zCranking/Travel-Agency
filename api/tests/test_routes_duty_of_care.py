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
