from fastapi import FastAPI

from routes.bookings import router as bookings_router
from routes.chat import router as chat_router

app = FastAPI(title="Wayfare API")
app.include_router(chat_router)
app.include_router(bookings_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
