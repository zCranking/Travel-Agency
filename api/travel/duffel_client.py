"""Duffel integration.

Two interchangeable clients, picked by `get_duffel_client()` from config:
MockDuffelClient (fixtures, zero credentials) and RealDuffelClient (live
Duffel REST API). They are duck-typed rather than sharing an ABC — one
method set, two implementations, no third coming.

ponytail: RealDuffelClient covers FLIGHTS only. Duffel Stays takes
lat/long + radius, not a city name, so real hotels need a geocoder the agent
doesn't have; hotel search and disruption lookups delegate to the mock. Add
Stays when a geocoding step earns its keep.
"""
import uuid
from decimal import Decimal

import httpx

from core.config import settings
from travel.models import BookingConfirmation, Disruption, FlightOption, HotelOption

_DUFFEL_API = "https://api.duffel.com"
_DUFFEL_VERSION = "v2"
# Duffel returns every fare its suppliers offer; the agent only needs a
# comparable handful to reason over, and fewer options is fewer tokens.
_MAX_OFFERS = 5

_FARE_CLASSES = ["economy", "premium_economy", "business"]
_AIRLINES = ["Skyward Air", "Continental Wing", "Pacific Crest"]
_HOTEL_BRANDS = ["Harborview Inn", "Cedar & Vine Hotel", "Meridian Suites"]


class MockDuffelClient:
    def search_flights(
        self, origin: str, destination: str, depart_date: str
    ) -> list[FlightOption]:
        return [
            FlightOption(
                id=str(uuid.uuid4()),
                airline=_AIRLINES[i % len(_AIRLINES)],
                fare_class=_FARE_CLASSES[i % len(_FARE_CLASSES)],
                origin=origin,
                destination=destination,
                depart_date=depart_date,
                price_cents=28000 + i * 15000,
            )
            for i in range(3)
        ]

    def search_hotels(
        self, location: str, check_in: str, check_out: str
    ) -> list[HotelOption]:
        return [
            HotelOption(
                id=str(uuid.uuid4()),
                name=_HOTEL_BRANDS[i % len(_HOTEL_BRANDS)],
                location=location,
                check_in=check_in,
                check_out=check_out,
                nightly_rate_cents=14000 + i * 8000,
            )
            for i in range(3)
        ]

    def book(
        self, option: FlightOption | HotelOption, traveler: dict | None = None
    ) -> BookingConfirmation:
        price = (
            option.price_cents
            if isinstance(option, FlightOption)
            else option.nightly_rate_cents
        )
        return BookingConfirmation(
            confirmation_code=f"WF{uuid.uuid4().hex[:8].upper()}",
            price_cents=price,
        )

    def get_disruption(self, details: dict) -> Disruption | None:
        """Mocked, deterministic: Pacific Crest flights are always shown as
        disrupted, everything else is clean. No real disruption feed exists
        yet — this proves the check_disruptions/rebooking path end to end
        against a stable fixture instead of random data."""
        if details.get("airline") == "Pacific Crest":
            return Disruption(
                type="delay",
                message="Pacific Crest flight delayed 3 hours due to crew scheduling.",
            )
        return None


def _to_cents(amount: str) -> int:
    """Duffel sends money as a decimal string ("1234.56"). Decimal, not float
    — binary floats round money wrong and this figure gets charged."""
    return int(Decimal(amount) * 100)


class LiveBookingNotAllowedError(RuntimeError):
    """Raised when a duffel_live_* token would issue a real, paid ticket
    without DUFFEL_ALLOW_LIVE_BOOKING=true having been set explicitly."""


class RealDuffelClient:
    """Live Duffel API. Same method set as MockDuffelClient."""

    def __init__(self, access_token: str, allow_live_booking: bool = False):
        self._token = access_token
        self._allow_live_booking = allow_live_booking
        self._mock = MockDuffelClient()  # hotels + disruptions, see module docstring

    @property
    def is_live(self) -> bool:
        """Duffel test tokens are prefixed `duffel_test_`. Anything else is
        treated as live — an unrecognised prefix must fail closed, not open."""
        return not self._token.startswith("duffel_test_")

    def _post(self, path: str, payload: dict) -> dict:
        response = httpx.post(
            f"{_DUFFEL_API}{path}",
            json={"data": payload},
            headers={
                "Authorization": f"Bearer {self._token}",
                "Duffel-Version": _DUFFEL_VERSION,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=60.0,  # airline supplier calls are genuinely slow
        )
        response.raise_for_status()
        return response.json()["data"]

    def search_flights(
        self, origin: str, destination: str, depart_date: str
    ) -> list[FlightOption]:
        data = self._post(
            "/air/offer_requests?return_offers=true",
            {
                "slices": [
                    {
                        "origin": origin,
                        "destination": destination,
                        "departure_date": depart_date,
                    }
                ],
                "passengers": [{"type": "adult"}],
            },
        )
        passenger_ids = [p["id"] for p in data.get("passengers", [])]
        offers = sorted(data.get("offers", []), key=lambda o: Decimal(o["total_amount"]))

        return [
            FlightOption(
                id=offer["id"],
                airline=offer["owner"]["name"],
                fare_class=_cabin_class(offer),
                origin=origin,
                destination=destination,
                depart_date=depart_date,
                price_cents=_to_cents(offer["total_amount"]),
                passenger_ids=passenger_ids,
                currency=offer["total_currency"],
            )
            for offer in offers[:_MAX_OFFERS]
        ]

    def search_hotels(
        self, location: str, check_in: str, check_out: str
    ) -> list[HotelOption]:
        return self._mock.search_hotels(location, check_in, check_out)

    def book(
        self, option: FlightOption | HotelOption, traveler: dict | None = None
    ) -> BookingConfirmation:
        if isinstance(option, HotelOption) or not option.passenger_ids:
            return self._mock.book(option)

        if self.is_live and not self._allow_live_booking:
            raise LiveBookingNotAllowedError(
                "Refusing to create a real, paid Duffel order: the configured "
                "token is not a duffel_test_* token and DUFFEL_ALLOW_LIVE_BOOKING "
                "is not true."
            )

        if not traveler:
            raise ValueError("Booking a real Duffel order requires traveler details.")

        amount = f"{Decimal(option.price_cents) / 100:.2f}"
        order = self._post(
            "/air/orders",
            {
                "selected_offers": [option.id],
                "payments": [
                    {"type": "balance", "currency": option.currency, "amount": amount}
                ],
                "passengers": [
                    {"id": passenger_id, **traveler} for passenger_id in option.passenger_ids
                ],
            },
        )
        return BookingConfirmation(
            confirmation_code=order["booking_reference"],
            price_cents=_to_cents(order["total_amount"]),
        )

    def get_disruption(self, details: dict) -> Disruption | None:
        return self._mock.get_disruption(details)


def _cabin_class(offer: dict) -> str:
    """Pull the cabin off the first segment. Duffel reports cabin per
    segment/passenger; a mixed-cabin itinerary is rare enough in this
    market that the first segment is the honest summary. Unknown or absent
    cabins fall back to 'first' — the HIGHEST fare rank, so an unmappable
    fare fails the policy check into human approval rather than silently
    passing as economy. Fail closed, not open."""
    try:
        segment = offer["slices"][0]["segments"][0]
        return segment["passengers"][0]["cabin_class"] or "first"
    except (KeyError, IndexError, TypeError):
        return "first"


def get_duffel_client() -> MockDuffelClient | RealDuffelClient:
    if not settings.duffel_access_token:
        return MockDuffelClient()
    return RealDuffelClient(
        settings.duffel_access_token, settings.duffel_allow_live_booking
    )
