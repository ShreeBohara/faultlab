"""Credential-free application startup and local health endpoint."""

from fastapi import FastAPI


app = FastAPI(title="FaultLab", version="0.1.0")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "faultlab-backend"}
