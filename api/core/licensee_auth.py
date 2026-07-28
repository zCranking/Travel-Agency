from fastapi import Header, HTTPException

from core.db import get_db


def require_licensee(x_api_key: str = Header(...)) -> dict:
    db = get_db()
    rows = db.table("licensees").select("id, name").eq("api_key", x_api_key).execute().data
    if not rows:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return rows[0]
