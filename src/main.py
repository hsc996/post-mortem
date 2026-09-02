from fastapi import FastAPI
from src.api.v1.auth import router as auth_router

app = FastAPI(title="PostMortem API", version="0.1.0")

app.include_router(auth_router, prefix="/api/v1")

@app.get("/healthz", status_code=200)
async def health_check():
    return {"status":"ok", "service":"PostMortem"}