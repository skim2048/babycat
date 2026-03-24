"""Watchdog API Server — placeholder (TODO: implement in Phase 1)"""

from fastapi import FastAPI

app = FastAPI(title="Watchdog API", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok"}
