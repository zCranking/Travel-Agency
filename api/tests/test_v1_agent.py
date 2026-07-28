from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


@patch("core.licensee_auth.get_db")
def test_v1_agent_message_requires_valid_api_key(mock_get_db):
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    mock_get_db.return_value = db

    response = client.post(
        "/v1/agent/message",
        json={"trip_id": "trip-1", "content": "hi"},
        headers={"X-API-Key": "not-a-real-key"},
    )

    assert response.status_code == 401


@patch("core.licensee_auth.get_db")
@patch("routes.v1_agent.handle_chat_message")
@patch("routes.v1_agent.get_db")
def test_v1_agent_message_success_with_valid_key(mock_get_db, mock_handle, mock_licensee_db):
    db = MagicMock()

    def table(name):
        t = MagicMock()
        if name == "licensees":
            t.select.return_value.eq.return_value.execute.return_value.data = [
                {"id": "lic-1", "name": "Wayfare Web"}
            ]
        return t

    db.table.side_effect = table
    mock_get_db.return_value = db
    mock_licensee_db.return_value = db
    mock_handle.return_value = "hello from the agent"

    response = client.post(
        "/v1/agent/message",
        json={"trip_id": "trip-1", "content": "hi"},
        headers={"X-API-Key": "real-key"},
    )

    assert response.status_code == 200
    assert response.json() == {"reply": "hello from the agent"}
    mock_handle.assert_called_once_with(db, "trip-1", "hi")
