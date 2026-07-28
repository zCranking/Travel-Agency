"""Expense-platform sync (Ramp/Brex/Concur). MockExpenseSyncClient today; a
RealExpenseSyncClient implementing the same sync_booking method is a
drop-in swap once a real expense-platform API key exists.
"""
import uuid

from pydantic import BaseModel


class SyncResult(BaseModel):
    synced: bool
    external_id: str | None


class MockExpenseSyncClient:
    def sync_booking(self, booking: dict) -> SyncResult:
        return SyncResult(synced=True, external_id=f"EXP-{uuid.uuid4().hex[:8].upper()}")
