import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.mitigation import MitigationState


async def get_mitigation_by_incident(
    db: AsyncSession, incident_id: uuid.UUID
) -> MitigationState | None:
    """Fetches the active mitigation for an incident, if one exists."""
    result = await db.execute(
        select(MitigationState).where(MitigationState.incident_id == incident_id)
    )
    return result.scalar_one_or_none()


async def get_mitigation_by_incident_or_404(
    db: AsyncSession, incident_id: uuid.UUID
) -> MitigationState:
    """Fetches the active mitigation for an incident, raising 404 if none exists."""
    mitigation = await get_mitigation_by_incident(db, incident_id)
    if mitigation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active mitigation found for incident {incident_id}.",
        )
    return mitigation
