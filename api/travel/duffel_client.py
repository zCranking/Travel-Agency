"""Duffel integration. MockDuffelClient returns fixture data today; a
RealDuffelClient implementing the same three methods is a drop-in swap once a
real Duffel API key exists — no call-site changes needed elsewhere.
"""
import uuid

from travel.models import BookingConfirmation, Disruption, FlightOption, HotelOption

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

    def book(self, option: FlightOption | HotelOption) -> BookingConfirmation:
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
