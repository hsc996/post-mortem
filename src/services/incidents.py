import uuid

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.incident import Incident
from src.models.user import User


async def ensure_assignee_exists(db: AsyncSession, assignee_id: uuid.UUID | None) -> None:
    """Validates that assignee_id, if provided, references an existing user."""
    if assignee_id is None:
        return
    result = await db.execute(select(User.id).where(User.id == assignee_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Assignee {assignee_id} does not exist.",
        )


async def get_incident_or_404(db: AsyncSession, incident_id: uuid.UUID) -> Incident:
    """Fetches an incident by ID, raising 404 if it doesn't exist."""
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found.",
        )
    return incident


async def apply_optimistic_update(
    db: AsyncSession,
    incident_id: uuid.UUID,
    expected_version: int,
    values: dict,
) -> None:
    """Conditionally updates an incident gated on its expected version (OCC)"""
    stmt = (
        update(Incident)
        .where(Incident.id == incident_id, Incident.version == expected_version)
        .values(version=Incident.version + 1, **values)
        .execution_options(synchronize_session="fetch")
    )
    result = await db.execute(stmt)

    if result.rowcount > 0:
        return

    current_version = (
        await db.execute(select(Incident.version).where(Incident.id == incident_id))
    ).scalar_one_or_none()

    if current_version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found.",
        )

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"Conflict: Incident was updated by another request. "
            f"Expected version {expected_version}, but current version is {current_version}."
        ),
    )
