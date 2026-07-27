from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from main import app

client = TestClient(app)


def _mock_db(history):
    """Fake supabase client: trips + policies lookups and trip_messages read."""
    db = MagicMock()

    def table(name):
        t = MagicMock()
        if name == "trips":
            t.select.return_value.eq.return_value.execute.return_value.data = [
                {"company_id": "company-1"}
            ]
        elif name == "policies":
            t.select.return_value.eq.return_value.execute.return_value.data = [
                {"id": "policy-1", "rules": {"max_fare_class": "economy"}}
            ]
        elif name == "trip_messages":
            t.select.return_value.eq.return_value.order.return_value.execute.return_value.data = (
                history
            )
        return t

    db.table.side_effect = table
    return db


@patch("routes.chat._graph")
@patch("routes.chat.get_db")
def test_post_message_passes_context_and_history(mock_get_db, mock_graph):
    history = [
        {"role": "user", "content": "earlier question"},
        {"role": "assistant", "content": "earlier answer"},
        {"role": "user", "content": "hi"},
    ]
    mock_get_db.return_value = _mock_db(history)
    mock_graph.invoke.return_value = {"messages": [AIMessage(content="hello back")]}

    response = client.post("/trips/trip-1/messages", json={"content": "hi"})

    assert response.status_code == 200
    assert response.json() == {"reply": "hello back"}

    invoked = mock_graph.invoke.call_args[0][0]["messages"]
    context = invoked[0]
    assert context["role"] == "system"
    assert "trip_id=trip-1" in context["content"]
    assert "policy_id=policy-1" in context["content"]
    assert "max_fare_class" in context["content"]  # rules included
    # prior history prepended, in order
    assert [m["content"] for m in invoked[1:]] == [
        "earlier question",
        "earlier answer",
        "hi",
    ]


@patch("routes.chat._graph")
@patch("routes.chat.get_db")
def test_post_message_404_when_trip_missing(mock_get_db, mock_graph):
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    mock_get_db.return_value = db

    response = client.post("/trips/nope/messages", json={"content": "hi"})

    assert response.status_code == 404
    mock_graph.invoke.assert_not_called()
