from unittest.mock import patch

import pytest

from travel.duffel_client import (
    LiveBookingNotAllowedError,
    MockDuffelClient,
    RealDuffelClient,
    get_duffel_client,
)
from travel.models import FlightOption

TEST_TOKEN = "duffel_test_abc"
LIVE_TOKEN = "duffel_live_abc"

OFFER_REQUEST_RESPONSE = {
    "id": "orq_1",
    "passengers": [{"id": "pas_1"}],
    "offers": [
        {
            "id": "off_expensive",
            "total_amount": "1200.50",
            "total_currency": "USD",
            "owner": {"name": "British Airways"},
            "slices": [{"segments": [{"passengers": [{"cabin_class": "business"}]}]}],
        },
        {
            "id": "off_cheap",
            "total_amount": "310.00",
            "total_currency": "USD",
            "owner": {"name": "United"},
            "slices": [{"segments": [{"passengers": [{"cabin_class": "economy"}]}]}],
        },
    ],
}

TRAVELER = {
    "given_name": "Jordan",
    "family_name": "Lee",
    "born_on": "1990-06-12",
    "gender": "m",
    "title": "mr",
    "phone_number": "+14155550142",
    "email": "jordan@acme-demo.test",
}


def _client(token=TEST_TOKEN, allow_live=False):
    return RealDuffelClient(token, allow_live)


@patch("travel.duffel_client.httpx.post")
def test_search_flights_maps_offers_cheapest_first(mock_post):
    mock_post.return_value.json.return_value = {"data": OFFER_REQUEST_RESPONSE}

    options = _client().search_flights("SFO", "JFK", "2026-09-01")

    assert [o.id for o in options] == ["off_cheap", "off_expensive"]
    cheapest = options[0]
    assert cheapest.airline == "United"
    assert cheapest.fare_class == "economy"
    assert cheapest.price_cents == 31000
    assert cheapest.currency == "USD"
    assert cheapest.passenger_ids == ["pas_1"]
    # origin/destination/date echo the request, not the response
    assert (cheapest.origin, cheapest.destination) == ("SFO", "JFK")


@patch("travel.duffel_client.httpx.post")
def test_search_flights_converts_money_without_float_error(mock_post):
    mock_post.return_value.json.return_value = {
        "data": {
            "passengers": [{"id": "pas_1"}],
            "offers": [
                {
                    "id": "off_1",
                    "total_amount": "1010.20",  # 101019.999... as a float
                    "total_currency": "USD",
                    "owner": {"name": "United"},
                    "slices": [
                        {"segments": [{"passengers": [{"cabin_class": "economy"}]}]}
                    ],
                }
            ],
        }
    }

    assert _client().search_flights("SFO", "JFK", "2026-09-01")[0].price_cents == 101020


@patch("travel.duffel_client.httpx.post")
def test_unmappable_cabin_fails_closed_to_highest_fare_rank(mock_post):
    """An offer with no readable cabin must not pass a fare-class policy
    check as economy — it should land at the most restrictive rank."""
    mock_post.return_value.json.return_value = {
        "data": {
            "passengers": [{"id": "pas_1"}],
            "offers": [
                {
                    "id": "off_1",
                    "total_amount": "500.00",
                    "total_currency": "USD",
                    "owner": {"name": "Mystery Air"},
                    "slices": [],
                }
            ],
        }
    }

    assert _client().search_flights("SFO", "JFK", "2026-09-01")[0].fare_class == "first"


@patch("travel.duffel_client.httpx.post")
def test_book_creates_order_and_returns_pnr(mock_post):
    mock_post.return_value.json.return_value = {
        "data": {"booking_reference": "PNR123", "total_amount": "310.00"}
    }
    option = FlightOption(
        id="off_cheap", airline="United", fare_class="economy", origin="SFO",
        destination="JFK", depart_date="2026-09-01", price_cents=31000,
        passenger_ids=["pas_1"], currency="USD",
    )

    confirmation = _client().book(option, TRAVELER)

    assert confirmation.confirmation_code == "PNR123"
    assert confirmation.price_cents == 31000
    payload = mock_post.call_args.kwargs["json"]["data"]
    assert payload["selected_offers"] == ["off_cheap"]
    assert payload["payments"][0] == {
        "type": "balance", "currency": "USD", "amount": "310.00"
    }
    assert payload["passengers"][0]["id"] == "pas_1"
    assert payload["passengers"][0]["given_name"] == "Jordan"


@patch("travel.duffel_client.httpx.post")
def test_book_refuses_live_token_without_explicit_opt_in(mock_post):
    option = FlightOption(
        id="off_1", airline="United", fare_class="economy", origin="SFO",
        destination="JFK", depart_date="2026-09-01", price_cents=31000,
        passenger_ids=["pas_1"],
    )

    with pytest.raises(LiveBookingNotAllowedError):
        _client(LIVE_TOKEN).book(option, TRAVELER)

    mock_post.assert_not_called()  # nothing hit the network, nothing was charged


def test_unrecognised_token_prefix_is_treated_as_live():
    """Fail closed: only an explicit duffel_test_ prefix counts as test mode."""
    assert _client("some_other_token").is_live is True
    assert _client(TEST_TOKEN).is_live is False


@patch("travel.duffel_client.httpx.post")
def test_book_requires_traveler_details(mock_post):
    option = FlightOption(
        id="off_1", airline="United", fare_class="economy", origin="SFO",
        destination="JFK", depart_date="2026-09-01", price_cents=31000,
        passenger_ids=["pas_1"],
    )

    with pytest.raises(ValueError, match="traveler details"):
        _client().book(option, None)

    mock_post.assert_not_called()


def test_get_duffel_client_returns_mock_without_a_token():
    with patch("travel.duffel_client.settings") as mock_settings:
        mock_settings.duffel_access_token = ""
        assert isinstance(get_duffel_client(), MockDuffelClient)


def test_get_duffel_client_returns_real_client_with_a_token():
    with patch("travel.duffel_client.settings") as mock_settings:
        mock_settings.duffel_access_token = TEST_TOKEN
        mock_settings.duffel_allow_live_booking = False
        assert isinstance(get_duffel_client(), RealDuffelClient)
