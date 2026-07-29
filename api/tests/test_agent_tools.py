from unittest.mock import patch

import pytest

import agent.tools
from agent.tools import create_booking, search_travel
from travel.duffel_client import DuffelAPIError

IN_POLICY_FLIGHT = {
    "id": "f9", "airline": "Skyward Air", "fare_class": "economy",
    "origin": "SFO", "destination": "JFK", "depart_date": "2026-09-01",
    "price_cents": 30000,
}
RULES = {
    "max_fare_class": "economy",
    "max_hotel_nightly_rate_cents": 25000,
    "advance_booking_days_required": 3,
    "approval_threshold_cents": 150000,
}


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


@patch("agent.tools.get_db")
def test_create_booking_books_in_policy_under_threshold(mock_get_db):
    mock_table = mock_get_db.return_value.table.return_value
    mock_table.insert.return_value.execute.return_value.data = [{"id": "booking-2"}]

    result = create_booking.invoke({
        "trip_id": "trip-1",
        "kind": "flight",
        "details": {
            "id": "f2", "airline": "Skyward Air", "fare_class": "economy",
            "origin": "SFO", "destination": "JFK", "depart_date": "2026-09-01",
            "price_cents": 30000,
        },
        "rules": {
            "max_fare_class": "economy",
            "max_hotel_nightly_rate_cents": 25000,
            "advance_booking_days_required": 3,
            "approval_threshold_cents": 150000,
        },
    })

    inserted = mock_table.insert.call_args[0][0]
    assert inserted["status"] == "booked"
    assert result["status"] == "booked"


@patch("agent.tools.get_db")
@patch.object(agent.tools._expense, "sync_booking", side_effect=Exception("sync down"))
def test_create_booking_succeeds_despite_expense_sync_failure(mock_sync_booking, mock_get_db):
    mock_table = mock_get_db.return_value.table.return_value
    mock_table.insert.return_value.execute.return_value.data = [{"id": "booking-3"}]

    result = create_booking.invoke({
        "trip_id": "trip-1",
        "kind": "flight",
        "details": {
            "id": "f3", "airline": "Skyward Air", "fare_class": "economy",
            "origin": "SFO", "destination": "JFK", "depart_date": "2026-09-01",
            "price_cents": 30000,
        },
        "rules": {
            "max_fare_class": "economy",
            "max_hotel_nightly_rate_cents": 25000,
            "advance_booking_days_required": 3,
            "approval_threshold_cents": 150000,
        },
    })

    inserted = mock_table.insert.call_args[0][0]
    assert inserted["status"] == "booked"
    assert result["status"] == "booked"
    assert mock_sync_booking.called  # Verify sync was attempted


@patch("agent.tools.issue_ticket")
@patch("agent.tools.get_db")
def test_create_booking_tickets_before_writing_a_booked_row(mock_get_db, mock_issue):
    mock_table = mock_get_db.return_value.table.return_value
    mock_table.insert.return_value.execute.return_value.data = [{"id": "booking-4"}]
    mock_issue.return_value = {**IN_POLICY_FLIGHT, "confirmation_code": "PNR777"}

    create_booking.invoke({
        "trip_id": "trip-1", "kind": "flight",
        "details": IN_POLICY_FLIGHT, "rules": RULES,
    })

    mock_issue.assert_called_once()
    # the persisted row carries the supplier's confirmation, not just a status
    assert mock_table.insert.call_args[0][0]["details"]["confirmation_code"] == "PNR777"


@patch("agent.tools.issue_ticket", side_effect=RuntimeError("airline rejected"))
@patch("agent.tools.get_db")
def test_create_booking_writes_no_row_when_ticketing_fails(mock_get_db, mock_issue):
    """A failed supplier call must leave no 'booked' row behind — a booking
    record that no airline has heard of is worse than no record at all."""
    mock_table = mock_get_db.return_value.table.return_value

    with pytest.raises(RuntimeError):
        create_booking.invoke({
            "trip_id": "trip-1", "kind": "flight",
            "details": IN_POLICY_FLIGHT, "rules": RULES,
        })

    mock_table.insert.assert_not_called()


@patch("agent.tools.issue_ticket")
@patch("agent.tools.get_db")
def test_create_booking_returns_a_stale_fare_instead_of_crashing_the_chat(
    mock_get_db, mock_issue
):
    """LangGraph re-raises non-ToolInvocationError exceptions, which would
    500 the chat. A stale fare must come back as a tool result the agent can
    act on — and must leave no booking row behind."""
    mock_table = mock_get_db.return_value.table.return_value
    mock_issue.side_effect = DuffelAPIError(
        code="offer_no_longer_available",
        message="Please select another offer.",
        status_code=422,
    )

    result = create_booking.invoke({
        "trip_id": "trip-1", "kind": "flight",
        "details": IN_POLICY_FLIGHT, "rules": RULES,
    })

    assert result["status"] == "unavailable"
    assert "select another offer" in result["error"]
    mock_table.insert.assert_not_called()


@patch("agent.tools._duffel")
def test_search_travel_returns_duffel_errors_rather_than_raising(mock_duffel):
    mock_duffel.search_flights.side_effect = DuffelAPIError(
        code="validation_error", message="SFX is not a valid airport code.",
        status_code=422,
    )

    result = search_travel.invoke({
        "kind": "flight", "origin_or_location": "SFX",
        "destination": "JFK", "date": "2026-09-01",
    })

    assert result == [{"error": "SFX is not a valid airport code."}]


@patch("agent.tools.issue_ticket")
@patch("agent.tools.get_db")
def test_create_booking_does_not_ticket_when_approval_is_needed(mock_get_db, mock_issue):
    mock_table = mock_get_db.return_value.table.return_value
    mock_table.insert.return_value.execute.return_value.data = [{"id": "booking-5"}]

    create_booking.invoke({
        "trip_id": "trip-1", "kind": "flight",
        "details": {**IN_POLICY_FLIGHT, "fare_class": "business"}, "rules": RULES,
    })

    mock_issue.assert_not_called()  # nothing is bought until a manager approves
