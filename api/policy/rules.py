"""Deterministic, cheap policy check — runs before any RAG lookup."""
from pydantic import BaseModel

from travel.models import FlightOption, HotelOption

_FARE_RANK = {"economy": 0, "premium_economy": 1, "business": 2}


class RuleCheckResult(BaseModel):
    in_policy: bool
    violations: list[str]
    requires_approval: bool


def check_rules(option: FlightOption | HotelOption, rules: dict) -> RuleCheckResult:
    violations: list[str] = []
    price_cents: int

    if isinstance(option, FlightOption):
        price_cents = option.price_cents
        max_class = rules["max_fare_class"]
        if _FARE_RANK[option.fare_class] > _FARE_RANK[max_class]:
            violations.append(
                f"fare_class '{option.fare_class}' exceeds max allowed '{max_class}'"
            )
    else:
        price_cents = option.nightly_rate_cents
        cap = rules["max_hotel_nightly_rate_cents"]
        if option.nightly_rate_cents > cap:
            violations.append(
                f"nightly_rate_cents {option.nightly_rate_cents} exceeds cap {cap}"
            )

    requires_approval = bool(violations) or price_cents > rules["approval_threshold_cents"]

    return RuleCheckResult(
        in_policy=not violations,
        violations=violations,
        requires_approval=requires_approval,
    )
