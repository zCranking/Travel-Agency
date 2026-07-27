"""RAG lookup for "why is this in/out of policy" — used only when the rules
check in policy/rules.py is ambiguous or the agent is asked to cite the
policy doc directly.
"""
from core.db import get_db
from policy.embeddings import embed


def ingest_policy_doc(policy_id: str, full_text: str) -> None:
    from policy.embeddings import chunk_text

    db = get_db()
    chunks = chunk_text(full_text)
    vectors = embed(chunks)
    db.table("policy_chunks").insert([
        {"policy_id": policy_id, "content": chunk, "embedding": vector}
        for chunk, vector in zip(chunks, vectors)
    ]).execute()


def answer_why(question: str, policy_id: str) -> str:
    db = get_db()
    query_vector = embed([question])[0]
    matches = db.rpc(
        "match_policy_chunks",
        {"query_embedding": query_vector, "match_policy_id": policy_id, "match_count": 3},
    ).execute().data
    if not matches:
        return "No matching policy clause found."
    return "\n".join(f"- {m['content']}" for m in matches)
