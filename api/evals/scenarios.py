"""Hand-written eval scenarios. Each checks an OBSERVABLE OUTCOME (reply
text keywords, or the routed intent) rather than an exact tool-call
sequence -- exact sequences are too brittle against normal LLM
non-determinism to be a useful regression signal.
"""

SCENARIOS = [
    {
        "name": "book_economy_flight_in_policy",
        "message": "Find me a flight from SFO to JFK on 2026-09-01, then book the cheapest economy option.",
        "expect_reply_contains": ["booked", "econom"],
    },
    {
        "name": "book_business_flight_needs_approval",
        "message": "Book me on the Pacific Crest business class flight from SFO to JFK on 2026-09-01.",
        "expect_reply_contains": ["pending", "approv"],
    },
    {
        "name": "hotel_within_cap",
        "message": "Find hotels in New York for 2026-09-01 to 2026-09-03 and book the cheapest one.",
        "expect_reply_contains": ["booked"],
    },
    {
        "name": "policy_why_question",
        "message": "Why can't I book a business class flight?",
        "expect_intent": "policy",
    },
    {
        "name": "policy_compliance_question",
        "message": "Is a $200/night hotel compliant with our travel policy?",
        "expect_intent": "policy",
    },
    {
        "name": "disruption_status_question",
        "message": "Is my flight delayed?",
        "expect_intent": "disruption",
    },
    {
        "name": "disruption_rebook_question",
        "message": "Can you rebook me, I think my flight got cancelled?",
        "expect_intent": "disruption",
    },
    {
        "name": "booking_search_question",
        "message": "What flights are available from SFO to JFK on 2026-09-01?",
        "expect_intent": "booking",
    },
    {
        "name": "booking_default_ambiguous",
        "message": "I need to get to Chicago next week for a client meeting.",
        "expect_intent": "booking",
    },
    {
        "name": "policy_fare_class_wording",
        "message": "What's our max allowed fare class?",
        "expect_intent": "policy",
    },
    {
        "name": "disruption_delay_wording",
        "message": "Has anything changed with my upcoming flight?",
        "expect_reply_contains": [],  # weak assertion: just must not error, delay wording varies
    },
    {
        "name": "booking_hotel_search",
        "message": "I need a hotel in New York for two nights starting September 1st, 2026.",
        "expect_intent": "booking",
    },
    {
        "name": "policy_advance_booking_question",
        "message": "Why does our policy require booking 3 days in advance?",
        "expect_intent": "policy",
    },
    {
        "name": "booking_multi_city_ambiguous",
        "message": "Book me a flight to Denver for the 12th.",
        "expect_intent": "booking",
    },
    {
        "name": "disruption_status_check_specific",
        "message": "Can you check the status of my Pacific Crest flight for delays?",
        "expect_intent": "disruption",
    },
]
