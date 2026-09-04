import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    action: str
    actor_id: uuid.UUID
    changes: dict[str, Any]
    ip_address: str | None
    incident_id: uuid.UUID | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
