from fastapi import FastAPI

app = FastAPI(title="Wayfare API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
