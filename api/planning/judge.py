"""Rank the feasible set and say why.

Everything numeric — totals, policy, soft violations — arrives as a *fact*
computed by code. The model weighs trade-offs and explains them; it does not
recompute them, and it cannot introduce an option the solver didn't produce.

The id validation is the Duffel offer-cache lesson generalised: a model
referencing an id the server never issued is not an answer, it's an invention.
"""
import json

from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel

from core.config import settings
from planning.models import Itinerary, Ranking, TripIntent

_PROMPT = (
    "You are Wayfare's trip planner. Every itinerary below already satisfies "
    "the traveler's hard constraints — you are choosing between valid options, "
    "not checking them. Rank them best-first for this traveler, and for each "
    "give a one-sentence rationale in terms of their own stated constraints, "
    "plus any concerns worth flagging. Weigh cost, timing, comfort and the "
    "listed policy/budget flags against each other. Rank every itinerary "
    "exactly once, and use only the itinerary ids given to you."
)


class Rankings(BaseModel):
    rankings: list[Ranking]


def _model():
    return ChatAnthropic(
        model="claude-sonnet-5", api_key=settings.anthropic_api_key
    ).with_structured_output(Rankings)


def _by_price(itineraries: list[Itinerary]) -> list[Ranking]:
    """Deterministic fallback. Cheapest first, honestly labelled — a degraded
    ranking beats a 500, and dressing it up as reasoning would be worse than
    either."""
    return [
        Ranking(
            itinerary_id=itinerary.id,
            rank=i + 1,
            rationale=f"${itinerary.total_price_cents / 100:,.0f} total.",
            concerns=[v.message for v in itinerary.soft_violations],
        )
        for i, itinerary in enumerate(
            sorted(itineraries, key=lambda x: x.total_price_cents)
        )
    ]


def _describe(itinerary: Itinerary) -> dict:
    return {
        "itinerary_id": itinerary.id,
        "total_price_cents": itinerary.total_price_cents,
        "legs": [
            {
                "route": f"{leg.origin}->{leg.destination}",
                "depart_at": leg.depart_at.isoformat(),
                "arrive_at": leg.arrive_at.isoformat(),
                "airline": leg.airline,
                "fare_class": leg.fare_class,
                "stops": leg.stops,
                "price_cents": leg.price_cents,
            }
            for leg in itinerary.legs
        ],
        "flags": [v.message for v in itinerary.soft_violations],
    }


def judge(itineraries: list[Itinerary], intent: TripIntent) -> list[Ranking]:
    if len(itineraries) <= 1:
        return _by_price(itineraries)   # nothing to weigh against anything

    known = {itinerary.id for itinerary in itineraries}
    payload = json.dumps({
        "origin_city": intent.origin_city,
        "preferences": intent.preferences,
        "budget_cents": intent.budget_cents,
        "meetings": [
            {
                "title": m.title, "city": m.city, "mode": m.mode,
                "starts_at": m.starts_at.isoformat(), "flexible": m.flexible,
            }
            for m in intent.meetings
        ],
        "itineraries": [_describe(i) for i in itineraries],
    })

    model = _model()
    for _ in range(2):   # one retry: a schema slip is usually not repeated
        try:
            result = model.invoke(
                [{"role": "system", "content": _PROMPT},
                 {"role": "user", "content": payload}]
            )
        except Exception:  # noqa: BLE001 — any model failure degrades, never raises
            break
        rankings = list(result.rankings)
        if rankings and all(r.itinerary_id in known for r in rankings):
            return sorted(rankings, key=lambda r: r.rank)

    return _by_price(itineraries)
