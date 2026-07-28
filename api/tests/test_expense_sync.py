from expense.sync_client import MockExpenseSyncClient


def test_sync_booking_returns_success_with_external_id():
    client = MockExpenseSyncClient()
    result = client.sync_booking({"id": "b1", "kind": "flight", "price_cents": 28000})
    assert result.synced is True
    assert result.external_id is not None
    assert result.external_id.startswith("EXP-")
