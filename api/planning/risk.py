"""Duty-of-care risk, derived from the itinerary itself.

Code extracts the factors; the model turns them into a severity and a concrete
recommendation. The factors ride along with the advisory so the assessment is
auditable — a wrong severity next to its evidence is visibly wrong, which is
more than could be said for the destination-hash placeholder this replaces.

No external risk feed. Everything here is a mechanical property of the plan.
"""
import json
import logging
from datetime import timedelta

from langchain_anthropic import ChatAnthropic

from core.config import settings
from planning.checkers import GROUND_BUFFER
from planning.models import Itinerary, RiskAssessment, RiskFactor, TripIntent

logger = logging.getLogger(__name__)

_LATE_ARRIVAL_FROM, _LATE_ARRIVAL_TO = 23, 5
_RED_EYE_FROM, _RED_EYE_TO = 22, 5
_EARLY_START_BEFORE = 8
_TIGHT_GROUND = timedelta(minutes=60)

_PROMPT = (
    "You are Wayfare's duty-of-care analyst. Given the mechanical risk factors "
    "of a business trip, give an overall severity (low/medium/high) and a "
    "short advisory naming the specific factors, plus concrete recommendations "
    "the traveler can act on. Do not invent factors that are not listed."
)


def _model():
    return ChatAnthropic(
        model="claude-sonnet-5", api_key=settings.anthropic_api_key
    ).with_structured_output(RiskAssessment)


def risk_factors(itinerary: Itinerary, intent: TripIntent) -> list[RiskFactor]:
    factors: list[RiskFactor] = []

    for leg in itinerary.legs:
        if leg.arrive_at.hour >= _LATE_ARRIVAL_FROM or leg.arrive_at.hour < _LATE_ARRIVAL_TO:
            factors.append(RiskFactor(
                code="late_arrival",
                detail=f"Lands in {leg.destination} at {leg.arrive_at:%H:%M} local.",
            ))
        if leg.depart_at.hour >= _RED_EYE_FROM or leg.depart_at.hour < _RED_EYE_TO:
            factors.append(RiskFactor(
                code="red_eye",
                detail=f"Departs {leg.origin} at {leg.depart_at:%H:%M} local.",
            ))
        if leg.stops >= 2:
            factors.append(RiskFactor(
                code="connections",
                detail=f"{leg.stops} connections on {leg.origin}->{leg.destination}.",
            ))

    dates = [leg.depart_at.date() for leg in itinerary.legs]
    if len(dates) != len(set(dates)):
        factors.append(RiskFactor(
            code="same_day_city_change",
            detail="Two flights on the same day.",
        ))

    for meeting in intent.in_person():
        if meeting.starts_at.hour < _EARLY_START_BEFORE:
            factors.append(RiskFactor(
                code="early_start",
                detail=f"{meeting.title!r} starts at {meeting.starts_at:%H:%M} local.",
            ))
        arrivals = [
            leg.arrive_at for leg in itinerary.legs
            if leg.destination == meeting.city and leg.arrive_at <= meeting.starts_at
        ]
        if not arrivals:
            continue
        landed = max(arrivals)
        if meeting.starts_at - landed < GROUND_BUFFER + _TIGHT_GROUND:
            factors.append(RiskFactor(
                code="tight_ground",
                detail=f"Under an hour of slack between landing and {meeting.title!r}.",
            ))
        # The planner books no hotel (Duffel Stays isn't integrated), so an
        # overnight shows up here as something the traveler must arrange.
        if landed.date() < meeting.starts_at.date():
            factors.append(RiskFactor(
                code="overnight_gap",
                detail=(
                    f"Overnight in {meeting.city} before {meeting.title!r}; "
                    "no hotel booked."
                ),
            ))

    return factors


def assess(itinerary: Itinerary, intent: TripIntent) -> RiskAssessment:
    factors = risk_factors(itinerary, intent)
    if not factors:
        # Paying a model to say nothing is wrong is exactly the decorative AI
        # this design exists to avoid.
        return RiskAssessment(severity="low", advisory="No risk factors identified.")

    try:
        assessment = _model().invoke(
            [{"role": "system", "content": _PROMPT},
             {"role": "user", "content": json.dumps([f.model_dump() for f in factors])}]
        )
    except Exception:  # degrade, never raise
        logger.warning("risk synthesis failed for %d factors", len(factors), exc_info=True)
        return RiskAssessment(
            severity="medium",
            advisory="Risk factors were identified but could not be summarised.",
            factors=factors,
        )

    assessment.factors = factors   # code's factors win; the model only summarises
    return assessment
