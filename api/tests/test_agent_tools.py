from unittest.mock import patch

from agent.tools import create_booking


@patch("agent.tools.get_db")
def test_create_booking_flags_out_of_policy_as_pending(mock_get_db):
    mock_table = mock_get_db.return_value.table.return_value
    mock_table.insert.return_value.execute.return_value.data = [{"id": "booking-1"}]

    result = create_booking.invoke({
        "trip_id": "trip-1",
        "kind": "flight",
        "details": {
            "id": "f1", "airline": "Skyward Air", "fare_class": "business",
            "origin": "SFO", "destination": "JFK", "depart_date": "2026-09-01",
            "price_cents": 90000,
        },
        "rules": {
            "max_fare_class": "economy",
            "max_hotel_nightly_rate_cents": 25000,
            "advance_booking_days_required": 3,
            "approval_threshold_cents": 150000,
        },
    })

    inserted = mock_table.insert.call_args[0][0]
    assert inserted["status"] == "pending_approval"
    assert result["status"] == "pending_approval"
