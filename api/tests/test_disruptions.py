from unittest.mock import patch

from agent.tools import check_disruptions
from travel.duffel_client import MockDuffelClient


def test_get_disruption_flags_pacific_crest_flights():
    client = MockDuffelClient()
    details = {"airline": "Pacific Crest", "origin": "SFO", "destination": "JFK"}
    disruption = client.get_disruption(details)
    assert disruption is not None
    assert disruption.type == "delay"
    assert "delayed" in disruption.message.lower()


def test_get_disruption_none_for_other_airlines():
    client = MockDuffelClient()
    details = {"airline": "Skyward Air", "origin": "SFO", "destination": "JFK"}
    assert client.get_disruption(details) is None


def test_get_disruption_none_for_hotels():
    client = MockDuffelClient()
    details = {"name": "Harborview Inn", "location": "NYC"}
    assert client.get_disruption(details) is None


@patch("agent.tools.get_db")
def test_check_disruptions_reports_only_affected_bookings(mock_get_db):
    mock_get_db.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "b1", "kind": "flight", "details": {"airline": "Pacific Crest", "origin": "SFO", "destination": "JFK"}},
        {"id": "b2", "kind": "flight", "details": {"airline": "Skyward Air", "origin": "SFO", "destination": "JFK"}},
        {"id": "b3", "kind": "hotel", "details": {"name": "Harborview Inn", "location": "NYC"}},
    ]

    result = check_disruptions.invoke({"trip_id": "trip-1"})

    assert len(result) == 1
    assert result[0]["booking_id"] == "b1"
    assert result[0]["type"] == "delay"
