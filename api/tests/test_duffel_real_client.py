from unittest.mock import patch

import httpx
import pytest

from travel.duffel_client import (
    OFFER_EXPIRED_CODE,
    DuffelAPIError,
    LiveBookingNotAllowedError,
    MockDuffelClient,
    RealDuffelClient,
    UnknownOfferError,
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


def _ok(mock_request, payload):
    """Configure a mocked httpx call as a successful Duffel response.
    status_code must be a real int — the error check compares it."""
    mock_request.return_value.status_code = 200
    mock_request.return_value.json.return_value = payload
    return mock_request


@patch("travel.duffel_client.httpx.post")
def test_search_flights_maps_offers_cheapest_first(mock_post):
    _ok(mock_post, {"data": OFFER_REQUEST_RESPONSE})

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
    _ok(mock_post, {
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
    })

    assert _client().search_flights("SFO", "JFK", "2026-09-01")[0].price_cents == 101020


@patch("travel.duffel_client.httpx.post")
def test_unmappable_cabin_fails_closed_to_highest_fare_rank(mock_post):
    """An offer with no readable cabin must not pass a fare-class policy
    check as economy — it should land at the most restrictive rank."""
    _ok(mock_post, {
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
    })

    assert _client().search_flights("SFO", "JFK", "2026-09-01")[0].fare_class == "first"


@patch("travel.duffel_client.httpx.post")
def test_book_creates_order_and_returns_pnr(mock_post):
    _ok(mock_post, {"data": {"booking_reference": "PNR123", "total_amount": "310.00"}})
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


@patch("travel.duffel_client.httpx.get")
@patch("travel.duffel_client.httpx.post")
def test_book_reconciles_an_order_that_timed_out(mock_post, mock_get):
    """A timeout doesn't mean the airline didn't ticket — if the order does
    exist, return it rather than stranding a real ticket with no record."""
    mock_post.side_effect = httpx.TimeoutException("read timed out")
    _ok(mock_get, {"data": [{"booking_reference": "5B32HW", "total_amount": "310.00"}]})
    option = FlightOption(
        id="off_1", airline="United", fare_class="economy", origin="SFO",
        destination="JFK", depart_date="2026-09-01", price_cents=31000,
        passenger_ids=["pas_1"],
    )

    confirmation = _client().book(option, TRAVELER)

    assert confirmation.confirmation_code == "5B32HW"
    assert mock_get.call_args.kwargs["params"] == {"offer_id": "off_1"}


@patch("travel.duffel_client.httpx.get")
@patch("travel.duffel_client.httpx.post")
def test_book_reraises_timeout_when_no_order_was_created(mock_post, mock_get):
    mock_post.side_effect = httpx.TimeoutException("read timed out")
    _ok(mock_get, {"data": []})
    option = FlightOption(
        id="off_1", airline="United", fare_class="economy", origin="SFO",
        destination="JFK", depart_date="2026-09-01", price_cents=31000,
        passenger_ids=["pas_1"],
    )

    with pytest.raises(httpx.TimeoutException):
        _client().book(option, TRAVELER)


@patch("travel.duffel_client.httpx.post")
def test_order_creation_uses_a_longer_timeout_than_search(mock_post):
    _ok(mock_post, {"data": {"booking_reference": "PNR1", "total_amount": "310.00"}})
    option = FlightOption(
        id="off_1", airline="United", fare_class="economy", origin="SFO",
        destination="JFK", depart_date="2026-09-01", price_cents=31000,
        passenger_ids=["pas_1"],
    )

    _client().book(option, TRAVELER)

    assert mock_post.call_args.kwargs["timeout"] > 60.0


@patch("travel.duffel_client.httpx.post")
def test_duffel_error_message_survives_instead_of_a_bare_status_code(mock_post):
    """The agent re-searches by reading this message, so it must not be
    flattened into '422 Unprocessable Entity'."""
    mock_post.return_value.status_code = 422
    mock_post.return_value.json.return_value = {
        "errors": [
            {
                "code": "offer_no_longer_available",
                "title": "Requested offer is no longer available",
                "message": "Please select another offer, or create a new offer request.",
            }
        ]
    }

    with pytest.raises(DuffelAPIError) as excinfo:
        _client().search_flights("SFO", "JFK", "2026-09-01")

    assert excinfo.value.code == OFFER_EXPIRED_CODE
    assert "select another offer" in excinfo.value.message
    assert "select another offer" in str(excinfo.value)


@patch("travel.duffel_client.httpx.post")
def test_non_json_error_body_still_raises(mock_post):
    mock_post.return_value.status_code = 500
    mock_post.return_value.json.side_effect = ValueError("not json")
    mock_post.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500", request=httpx.Request("POST", "https://api.duffel.com"),
        response=httpx.Response(500),
    )

    with pytest.raises(httpx.HTTPStatusError):
        _client().search_flights("SFO", "JFK", "2026-09-01")


@patch("travel.duffel_client.httpx.post")
def test_book_refuses_an_offer_that_was_never_searched(mock_post):
    """The agent hallucinated 'frontier-sfo-jfk-2026-09-11' as an offer id in
    live testing. An id we never issued must fail, not book something."""
    option = FlightOption(
        id="frontier-sfo-jfk-2026-09-11", airline="Frontier", fare_class="economy",
        origin="SFO", destination="JFK", depart_date="2026-09-11", price_cents=16899,
    )

    with pytest.raises(UnknownOfferError):
        _client().book(option, TRAVELER)

    mock_post.assert_not_called()


@patch("travel.duffel_client.httpx.post")
def test_book_recovers_passenger_ids_and_price_the_model_dropped(mock_post):
    """The agent re-types options and loses passenger_ids / edits the price.
    The cached offer from search is authoritative for what gets bought."""
    _ok(mock_post, {"data": OFFER_REQUEST_RESPONSE})
    _client().search_flights("SFO", "JFK", "2026-09-01")

    # what the model hands back: right id, no passenger ids, wrong price
    mangled = FlightOption(
        id="off_cheap", airline="United", fare_class="economy", origin="SFO",
        destination="JFK", depart_date="2026-09-01", price_cents=99999,
    )
    _ok(mock_post, {"data": {"booking_reference": "PNR9", "total_amount": "310.00"}})

    confirmation = _client().book(mangled, TRAVELER)

    payload = mock_post.call_args.kwargs["json"]["data"]
    assert payload["passengers"][0]["id"] == "pas_1"        # recovered
    assert payload["payments"][0]["amount"] == "310.00"     # cached, not 999.99
    assert confirmation.price_cents == 31000


@patch("travel.duffel_client.httpx.post")
def test_a_real_client_never_falls_back_to_a_mock_confirmation(mock_post):
    """A 'booked' row carrying a WF******** mock code is the phantom booking
    this client exists to prevent."""
    option = FlightOption(
        id="off_never_offered", airline="United", fare_class="economy",
        origin="SFO", destination="JFK", depart_date="2026-09-01",
        price_cents=31000,
    )

    with pytest.raises(UnknownOfferError):
        _client().book(option, TRAVELER)


def test_get_duffel_client_returns_mock_without_a_token():
    with patch("travel.duffel_client.settings") as mock_settings:
        mock_settings.duffel_access_token = ""
        assert isinstance(get_duffel_client(), MockDuffelClient)


def test_get_duffel_client_returns_real_client_with_a_token():
    with patch("travel.duffel_client.settings") as mock_settings:
        mock_settings.duffel_access_token = TEST_TOKEN
        mock_settings.duffel_allow_live_booking = False
        assert isinstance(get_duffel_client(), RealDuffelClient)
