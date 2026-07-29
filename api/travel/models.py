from pydantic import BaseModel


class FlightOption(BaseModel):
    id: str  # Duffel offer id when real, opaque uuid when mocked
    airline: str
    fare_class: str  # "economy" | "premium_economy" | "business" | "first"
    origin: str
    destination: str
    depart_date: str
    price_cents: int
    # Duffel assigns passenger ids at offer-request time and requires them back
    # at order time; carried on the option so booking needs no second search.
    # Empty for mock options, which is how `book()` tells the two apart.
    passenger_ids: list[str] = []
    currency: str = "USD"


class HotelOption(BaseModel):
    id: str
    name: str
    location: str
    check_in: str
    check_out: str
    nightly_rate_cents: int


class BookingConfirmation(BaseModel):
    confirmation_code: str
    price_cents: int


class Disruption(BaseModel):
    type: str  # "delay" | "cancellation"
    message: str
