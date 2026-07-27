from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.bookings import router as bookings_router
from routes.chat import router as chat_router

app = FastAPI(title="Wayfare API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(chat_router)
app.include_router(bookings_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
