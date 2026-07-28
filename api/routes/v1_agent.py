from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.db import get_db
from core.licensee_auth import require_licensee
from routes.chat import handle_chat_message

router = APIRouter(prefix="/v1")


class AgentMessageIn(BaseModel):
    trip_id: str
    content: str


@router.post("/agent/message")
def v1_agent_message(body: AgentMessageIn, licensee: dict = Depends(require_licensee)) -> dict:  # noqa: B008
    db = get_db()

    trips = db.table("trips").select("company_id").eq("id", body.trip_id).execute().data
    if not trips or trips[0]["company_id"] != licensee["company_id"]:
        raise HTTPException(status_code=403, detail="Trip does not belong to this licensee")

    reply = handle_chat_message(db, body.trip_id, body.content)
    return {"reply": reply}
