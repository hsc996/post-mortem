import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from src.models.incident import IncidentSeverity, IncidentStatus

class IncidentCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    description: str = Field(..., min_length=1, max_length=10_000)
    service_name: str = Field(..., min_length=3, max_length=100)
    severity: IncidentSeverity = IncidentSeverity.MEDIUM
    assignee_id: uuid.UUID | None = None

class IncidentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=10_000)
    service_name: str | None = Field(default=None, min_length=3, max_length=100)
    severity: IncidentSeverity | None = None
    status: IncidentStatus | None = None
    assignee_id: uuid.UUID | None = None
    version: int = Field(
        ..., description="The expected version integer for optimistic locking"
    )

class IncidentResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    service_name: str
    severity: IncidentSeverity
    status: IncidentStatus
    version: int
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    mttr_seconds: float | None = None
    reporter_id: uuid.UUID
    assignee_id: uuid.UUID | None = None

    model_config = ConfigDict(from_attributes=True)
