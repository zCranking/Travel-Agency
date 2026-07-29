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
    # ISO 8601 *with* offset. A solver reasoning about "land before the 2pm
    # meeting" needs an instant, not a date; the offset is what makes a Denver
    # arrival and a Chicago meeting comparable. Blank when the source doesn't
    # supply times (seeded rows, older fixtures) — such an option is still
    # bookable through chat, it just can't take part in constraint solving.
    depart_at: str = ""
    arrive_at: str = ""
    stops: int = 0


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
