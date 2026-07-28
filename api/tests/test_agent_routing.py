from langgraph.graph.message import add_messages

from agent.graph import _last_human_text, classify_intent


def test_classify_intent_routes_disruption_keywords():
    assert classify_intent("Is my flight delayed?") == "disruption"
    assert classify_intent("Was my trip cancelled?") == "disruption"
    assert classify_intent("Can you rebook me on a different flight?") == "disruption"


def test_classify_intent_routes_policy_keywords():
    assert classify_intent("Why is business class not allowed?") == "policy"
    assert classify_intent("Is this hotel compliant with our policy?") == "policy"


def test_classify_intent_defaults_to_booking():
    assert classify_intent("Find me a flight from SFO to JFK on 2026-09-01") == "booking"
    assert classify_intent("Book the economy option") == "booking"


def test_last_human_text_reads_coerced_message_objects():
    # add_messages coerces raw dicts into HumanMessage/AIMessage — the real
    # runtime case the graph feeds _last_human_text, not plain dicts.
    coerced = add_messages([], [{"role": "user", "content": "Is my flight delayed?"}])
    assert _last_human_text({"messages": coerced}) == "Is my flight delayed?"


def test_last_human_text_picks_last_human_turn():
    coerced = add_messages(
        [],
        [
            {"role": "user", "content": "first question"},
            {"role": "assistant", "content": "an answer"},
            {"role": "user", "content": "Is my flight delayed?"},
        ],
    )
    assert _last_human_text({"messages": coerced}) == "Is my flight delayed?"
