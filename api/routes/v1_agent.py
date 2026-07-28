from fastapi import APIRouter, Depends
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
    reply = handle_chat_message(db, body.trip_id, body.content)
    return {"reply": reply}
