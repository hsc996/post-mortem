import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class MitigationCreate(BaseModel):
    summary: str = Field(
        ..., min_length=5, max_length=2_000, description="Brief explanation of the workaround/patch"
    )
    ttl_minutes: int = Field(
        ..., ge=1, le=10080, description="Time-to-live in minutes before mitigation expires (1 min to 7 days)"
    )

class MitigationResponse(BaseModel):
    id: uuid.UUID
    incident_id: uuid.UUID
    summary: str
    ttl_minutes: int
    applied_at: datetime
    applied_by_id: uuid.UUID
    is_expired: bool

    model_config = ConfigDict(from_attributes=True)
