from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.graph import build_agent_graph
from core.db import get_db

router = APIRouter()
_graph = build_agent_graph()


class MessageIn(BaseModel):
    content: str


def extract_reply_text(content: str | list) -> str:
    """Claude's message content is a plain string for simple replies, but a
    list of content blocks (thinking/text/tool_use) whenever extended
    thinking is involved. Only text blocks are a reply; thinking blocks
    carry an internal reasoning signature that must never reach the client.
    """
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )


@router.post("/trips/{trip_id}/messages")
def post_message(trip_id: str, message: MessageIn) -> dict:
    db = get_db()

    trips = db.table("trips").select("company_id").eq("id", trip_id).execute().data
    if not trips:
        raise HTTPException(status_code=404, detail="Trip not found")
    company_id = trips[0]["company_id"]

    policies = (
        db.table("policies").select("id, rules").eq("company_id", company_id).execute().data
    )
    if not policies:
        raise HTTPException(status_code=404, detail="Policy not found for company")
    policy_id = policies[0]["id"]
    rules = policies[0]["rules"]

    db.table("trip_messages").insert(
        {"trip_id": trip_id, "role": "user", "content": message.content}
    ).execute()

    # History includes the just-inserted user message (last), so we don't append it again.
    history = (
        db.table("trip_messages")
        .select("role, content")
        .eq("trip_id", trip_id)
        .order("created_at")
        .execute()
        .data
    )

    context = (
        f"Context for tool calls: trip_id={trip_id}, rules={rules}, policy_id={policy_id}. "
        "Always pass these exact values when calling check_policy, why_out_of_policy, "
        "or create_booking."
    )
    messages = [
        {"role": "system", "content": context},
        *[{"role": m["role"], "content": m["content"]} for m in history],
    ]

    result = _graph.invoke({"messages": messages})
    reply = extract_reply_text(result["messages"][-1].content)

    db.table("trip_messages").insert(
        {"trip_id": trip_id, "role": "assistant", "content": reply}
    ).execute()

    return {"reply": reply}
