from agent.graph import classify_intent


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
