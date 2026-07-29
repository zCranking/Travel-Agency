from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

PENDING = {
    "id": "b1",
    "trip_id": "trip-1",
    "kind": "flight",
    "status": "pending_approval",
    "details": {"id": "off_1", "airline": "Skyward Air"},
}


def _select_returns(mock_get_db, rows):
    mock_get_db.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value.data = rows
    return mock_get_db.return_value.table.return_value


@patch("routes.bookings.issue_ticket")
@patch("routes.bookings.get_db")
def test_approve_booking_tickets_then_marks_booked(mock_get_db, mock_issue):
    table = _select_returns(mock_get_db, [PENDING])
    table.update.return_value.eq.return_value.execute.return_value.data = [
        {"id": "b1", "status": "booked"}
    ]
    mock_issue.return_value = {**PENDING["details"], "confirmation_code": "ABC123"}

    response = client.post("/bookings/b1/approve")

    assert response.status_code == 200
    mock_issue.assert_called_once_with(
        mock_get_db.return_value, "trip-1", "flight", PENDING["details"]
    )
    table.update.assert_called_with(
        {"status": "booked", "details": {**PENDING["details"], "confirmation_code": "ABC123"}}
    )


@patch("routes.bookings.issue_ticket")
@patch("routes.bookings.get_db")
def test_approve_booking_is_idempotent_and_does_not_double_ticket(mock_get_db, mock_issue):
    _select_returns(mock_get_db, [{**PENDING, "status": "booked"}])

    response = client.post("/bookings/b1/approve")

    assert response.status_code == 200
    mock_issue.assert_not_called()


@patch("routes.bookings.issue_ticket")
@patch("routes.bookings.get_db")
def test_approve_booking_409s_when_fare_expired(mock_get_db, mock_issue):
    table = _select_returns(mock_get_db, [PENDING])
    mock_issue.side_effect = httpx.HTTPStatusError(
        "expired", request=httpx.Request("POST", "https://api.duffel.com"),
        response=httpx.Response(422),
    )

    response = client.post("/bookings/b1/approve")

    assert response.status_code == 409
    # the row must NOT be marked booked when ticketing failed
    table.update.assert_not_called()


@patch("routes.bookings.get_db")
def test_approve_booking_returns_404_when_not_found(mock_get_db):
    _select_returns(mock_get_db, [])

    response = client.post("/bookings/missing/approve")

    assert response.status_code == 404
