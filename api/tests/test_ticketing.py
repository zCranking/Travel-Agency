from unittest.mock import MagicMock, patch

from travel.ticketing import get_traveler, issue_ticket

FLIGHT = {
    "id": "off_1", "airline": "United", "fare_class": "economy",
    "origin": "SFO", "destination": "JFK", "depart_date": "2026-09-01",
    "price_cents": 31000,
}
PROFILE = {
    "given_name": "Jordan", "family_name": "Lee", "born_on": "1990-06-12",
    "gender": "m", "title": "mr", "phone_number": "+14155550142",
}


def _db(trips, employees):
    db = MagicMock()

    def table(name):
        t = MagicMock()
        rows = trips if name == "trips" else employees
        t.select.return_value.eq.return_value.execute.return_value.data = rows
        return t

    db.table.side_effect = table
    return db


def test_get_traveler_merges_profile_with_login_email():
    db = _db([{"employee_id": "emp-1"}], [
        {"email": "jordan@acme-demo.test", "traveler_profile": PROFILE}
    ])

    traveler = get_traveler(db, "trip-1")

    assert traveler == {**PROFILE, "email": "jordan@acme-demo.test"}


def test_get_traveler_returns_none_when_profile_missing():
    db = _db([{"employee_id": "emp-1"}], [
        {"email": "sam@acme-demo.test", "traveler_profile": None}
    ])

    assert get_traveler(db, "trip-1") is None


def test_get_traveler_returns_none_for_unknown_trip():
    assert get_traveler(_db([], []), "nope") is None


@patch("travel.ticketing.get_duffel_client")
def test_issue_ticket_adds_confirmation_code_to_details(mock_get_client):
    mock_get_client.return_value.book.return_value = MagicMock(
        confirmation_code="PNR999"
    )
    db = _db([{"employee_id": "emp-1"}], [
        {"email": "jordan@acme-demo.test", "traveler_profile": PROFILE}
    ])

    details = issue_ticket(db, "trip-1", "flight", FLIGHT)

    assert details == {**FLIGHT, "confirmation_code": "PNR999"}
    # the traveler payload reaches the supplier — booking without it would
    # either fail at Duffel or ticket the wrong person
    _option, traveler = mock_get_client.return_value.book.call_args[0]
    assert traveler["family_name"] == "Lee"
