from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


@patch("routes.bookings.get_db")
def test_approve_booking_updates_status(mock_get_db):
    mock_table = mock_get_db.return_value.table.return_value
    mock_table.update.return_value.eq.return_value.execute.return_value.data = [
        {"id": "b1", "status": "booked"}
    ]

    response = client.post("/bookings/b1/approve")

    assert response.status_code == 200
    mock_table.update.assert_called_with({"status": "booked"})


@patch("routes.bookings.get_db")
def test_approve_booking_returns_404_when_not_found(mock_get_db):
    mock_table = mock_get_db.return_value.table.return_value
    mock_table.update.return_value.eq.return_value.execute.return_value.data = []

    response = client.post("/bookings/missing/approve")

    assert response.status_code == 404
