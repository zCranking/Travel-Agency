"""Prose (or a pasted invite) -> a *draft* set of meetings.

Draft is the whole point. The output populates the meeting form and the
traveler confirms it; nothing is solved or booked from an uninspected model
reading. Making someone type structured data as prose so a model can parse it
back would be a form with extra latency and a failure mode — the form is the
primary path and this is the accelerant for input that arrives messy, which
meeting invitations invariably do.

Anything ambiguous lands in `unresolved` rather than being guessed. A guessed
city books a real ticket to the wrong place.
"""
from datetime import date

from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field

from core.config import settings
from planning.models import Meeting

_PROMPT = (
    "Extract business meetings from the text into structured form. Today is "
    "{today}; resolve relative dates against it. Use IATA airport codes for "
    "cities (Chicago -> ORD, Denver -> DEN, San Francisco -> SFO). Mark a "
    "meeting in_person only when the text says or clearly implies the traveler "
    "must physically attend; otherwise virtual. Mark flexible only when the "
    "text says it can be moved, skipped, or taken from anywhere. Every meeting "
    "needs a timezone-aware start and end, in the local zone of its city. "
    "If anything is ambiguous — an unclear city, a date you cannot resolve, a "
    "missing time — do NOT guess: describe what you could not determine in "
    "`unresolved` and leave that meeting out."
)


class TripIntentDraft(BaseModel):
    origin_city: str | None = None
    meetings: list[Meeting] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)


def _model():
    return ChatAnthropic(
        model="claude-sonnet-5", api_key=settings.anthropic_api_key
    ).with_structured_output(TripIntentDraft)


def interpret(text: str, today: date) -> TripIntentDraft:
    try:
        return _model().invoke(
            [{"role": "system", "content": _PROMPT.format(today=today.isoformat())},
             {"role": "user", "content": text}]
        )
    except Exception:  # noqa: BLE001 — say so, rather than silently returning nothing
        return TripIntentDraft(
            unresolved=["Could not read that description — add the meetings manually."]
        )
