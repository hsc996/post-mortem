from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from src.api.v1.audit import router as audit_router
from src.api.v1.auth import router as auth_router
from src.api.v1.incidents import router as incident_router
from src.api.v1.mitigations import router as mitigation_router
from src.config import settings
from src.core.rate_limit import limiter

app = FastAPI(title="PostMortem API", version="0.1.0")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(incident_router, prefix="/api/v1")
app.include_router(mitigation_router, prefix="/api/v1")
app.include_router(audit_router, prefix="/api/v1")

@app.get("/healthz", status_code=200)
async def health_check():
    return {"status":"ok", "service":"PostMortem"}
