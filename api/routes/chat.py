from fastapi import APIRouter
from pydantic import BaseModel

from agent.graph import build_agent_graph
from core.db import get_db

router = APIRouter()
_graph = build_agent_graph()


class MessageIn(BaseModel):
    content: str


@router.post("/trips/{trip_id}/messages")
def post_message(trip_id: str, message: MessageIn) -> dict:
    db = get_db()
    db.table("trip_messages").insert(
        {"trip_id": trip_id, "role": "user", "content": message.content}
    ).execute()

    result = _graph.invoke({"messages": [{"role": "user", "content": message.content}]})
    reply = result["messages"][-1].content

    db.table("trip_messages").insert(
        {"trip_id": trip_id, "role": "assistant", "content": reply}
    ).execute()

    return {"reply": reply}
