from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock, patch

from planning.interpret import TripIntentDraft, interpret
from planning.judge import judge
from planning.models import Itinerary, Leg, Meeting, Ranking, RiskAssessment, TripIntent
from planning.risk import assess, risk_factors


def at(day, hour, minute=0):
    return datetime(2026, 9, day, hour, minute, tzinfo=UTC)


def leg(origin="SFO", dest="ORD", depart=None, hours=4, price=30000, stops=0):
    depart = depart or at(1, 9)
    return Leg(
        origin=origin, destination=dest, depart_at=depart,
        arrive_at=depart + timedelta(hours=hours), airline="United",
        fare_class="economy", price_cents=price, stops=stops,
    )


def itinerary(iid, legs=None, price=30000):
    built = Itinerary.from_legs(legs or [leg(price=price)])
    built.id = iid
    return built


def meeting(title, city, start, end):
    return Meeting(id="m", title=title, city=city, mode="in_person",
                   starts_at=start, ends_at=end)


# --- judge ----------------------------------------------------------------

@patch("planning.judge._model")
def test_judge_returns_the_models_ranking_when_every_id_is_real(mock_model):
    options = [itinerary("a"), itinerary("b")]
    mock_model.return_value.invoke.return_value = MagicMock(rankings=[
        Ranking(itinerary_id="b", rank=1, rationale="Cheaper and earlier"),
        Ranking(itinerary_id="a", rank=2, rationale="Backup"),
    ])

    result = judge(options, TripIntent(origin_city="SFO"))

    assert [r.itinerary_id for r in result] == ["b", "a"]


@patch("planning.judge._model")
def test_judge_refuses_a_ranking_that_names_an_itinerary_we_never_produced(mock_model):
    """The same lesson as the Duffel offer cache: a model referencing an id the
    server never issued is not a ranking, it's an invention."""
    options = [itinerary("a"), itinerary("b")]
    mock_model.return_value.invoke.return_value = MagicMock(rankings=[
        Ranking(itinerary_id="does-not-exist", rank=1, rationale="Best value"),
    ])

    result = judge(options, TripIntent(origin_city="SFO"))

    assert {r.itinerary_id for r in result} == {"a", "b"}    # deterministic fallback
    assert mock_model.return_value.invoke.call_count == 2    # one retry, then fall back


@patch("planning.judge._model")
def test_judge_falls_back_to_price_order_when_the_model_raises(mock_model):
    """A misbehaving model degrades output quality; it never 500s the plan."""
    mock_model.return_value.invoke.side_effect = RuntimeError("overloaded")
    options = [itinerary("expensive", price=90000), itinerary("cheap", price=20000)]

    result = judge(options, TripIntent(origin_city="SFO"))

    assert [r.itinerary_id for r in result] == ["cheap", "expensive"]
    assert result[0].rank == 1
    assert result[0].rationale


def test_judge_short_circuits_a_single_itinerary_without_calling_a_model():
    """Nothing to weigh against anything. Paying for a model call to rank one
    option is exactly the decorative AI this project pivoted away from."""
    with patch("planning.judge._model") as mock_model:
        result = judge([itinerary("only")], TripIntent(origin_city="SFO"))

    mock_model.assert_not_called()
    assert [r.itinerary_id for r in result] == ["only"]


# --- risk -----------------------------------------------------------------

def test_risk_factors_flag_a_late_arrival_and_an_early_start():
    plan = itinerary("a", [leg(depart=at(1, 19), hours=5)])   # lands 00:00
    intent = TripIntent(origin_city="SFO",
                        meetings=[meeting("Standup", "ORD", at(2, 7), at(2, 8))])

    codes = {factor.code for factor in risk_factors(plan, intent)}

    assert "late_arrival" in codes
    assert "early_start" in codes


def test_risk_factors_flag_a_tight_connection_to_the_meeting():
    plan = itinerary("a", [leg(depart=at(1, 8), hours=4)])    # lands 12:00
    intent = TripIntent(origin_city="SFO",
                        meetings=[meeting("Pitch", "ORD", at(1, 14), at(1, 15))])

    assert "tight_ground" in {f.code for f in risk_factors(plan, intent)}


def test_risk_factors_flag_an_overnight_with_no_hotel_booked():
    plan = itinerary("a", [leg(depart=at(1, 14), hours=4)])   # lands 18:00 the day before
    intent = TripIntent(origin_city="SFO",
                        meetings=[meeting("Standup", "ORD", at(2, 9), at(2, 10))])

    assert "overnight_gap" in {f.code for f in risk_factors(plan, intent)}


def test_risk_factors_flag_multiple_stops():
    plan = itinerary("a", [leg(stops=2)])
    codes = {f.code for f in risk_factors(plan, TripIntent(origin_city="SFO"))}
    assert "connections" in codes


def test_a_clean_itinerary_produces_low_risk_with_no_model_call():
    """No factors means nothing to synthesise. Paying a model to say nothing is
    wrong is the kind of thing this design exists to avoid."""
    plan = itinerary("a", [leg(depart=at(1, 9), hours=4)])    # lands 13:00
    intent = TripIntent(origin_city="SFO",
                        meetings=[meeting("Dinner", "ORD", at(1, 19), at(1, 21))])

    with patch("planning.risk._model") as mock_model:
        assessment = assess(plan, intent)

    mock_model.assert_not_called()
    assert assessment.severity == "low"
    assert assessment.factors == []


@patch("planning.risk._model")
def test_assess_synthesises_factors_into_an_advisory(mock_model):
    mock_model.return_value.invoke.return_value = RiskAssessment(
        severity="high",
        advisory="Lands after midnight with a 7am start.",
        recommendations=["Book the airport hotel, not downtown."],
    )
    plan = itinerary("a", [leg(depart=at(1, 19), hours=5)])
    intent = TripIntent(origin_city="SFO",
                        meetings=[meeting("Standup", "ORD", at(2, 7), at(2, 8))])

    assessment = assess(plan, intent)

    assert assessment.severity == "high"
    assert assessment.recommendations
    # factors travel with the advisory so a wrong severity is visibly wrong
    assert {f.code for f in assessment.factors} >= {"late_arrival", "early_start"}


@patch("planning.risk._model")
def test_assess_degrades_to_medium_when_the_model_fails(mock_model):
    mock_model.return_value.invoke.side_effect = RuntimeError("overloaded")
    plan = itinerary("a", [leg(depart=at(1, 19), hours=5)])
    intent = TripIntent(origin_city="SFO",
                        meetings=[meeting("Standup", "ORD", at(2, 7), at(2, 8))])

    assessment = assess(plan, intent)

    assert assessment.severity == "medium"     # factors exist, synthesis didn't
    assert assessment.factors


# --- interpret ------------------------------------------------------------

@patch("planning.interpret._model")
def test_interpret_returns_a_draft_the_traveler_confirms(mock_model):
    mock_model.return_value.invoke.return_value = TripIntentDraft(
        origin_city="SFO",
        meetings=[meeting("Client pitch", "ORD", at(1, 19), at(1, 20))],
    )

    draft = interpret("Chicago Tuesday 2pm for a client pitch", date(2026, 8, 25))

    assert draft.meetings[0].city == "ORD"
    assert draft.unresolved == []


@patch("planning.interpret._model")
def test_interpret_surfaces_what_it_could_not_work_out_rather_than_guessing(mock_model):
    """A guessed city books a real ticket to the wrong place. The draft says
    'I couldn't tell' and the traveler fills it in."""
    mock_model.return_value.invoke.return_value = TripIntentDraft(
        origin_city="SFO",
        unresolved=["Couldn't tell which city 'the usual place' means"],
    )

    draft = interpret("meet at the usual place Tuesday", date(2026, 8, 25))

    assert draft.meetings == []
    assert draft.unresolved


@patch("planning.interpret._model")
def test_interpret_returns_an_empty_draft_when_the_model_fails(mock_model):
    mock_model.return_value.invoke.side_effect = RuntimeError("overloaded")

    draft = interpret("anything", date(2026, 8, 25))

    assert draft.meetings == []
    assert draft.unresolved      # says so, rather than silently returning nothing
