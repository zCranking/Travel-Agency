from pydantic import BaseModel


class FlightOption(BaseModel):
    id: str
    airline: str
    fare_class: str  # "economy" | "premium_economy" | "business"
    origin: str
    destination: str
    depart_date: str
    price_cents: int


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
