import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user, RequireRole
from src.core.database import get_db
from src.models.incident import Incident, IncidentSeverity, IncidentStatus
from src.models.user import User, UserRole
from src.schemas.incident import IncidentCreate, IncidentUpdate, IncidentResponse
from src.services.incidents import (
    apply_optimistic_update,
    ensure_assignee_exists,
    get_incident_or_404,
    record_audit_log,
)

router = APIRouter(prefix="/incidents", tags=["Incidents"])

@router.post("/", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
async def create_incident(
    incident_in: IncidentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        RequireRole([UserRole.ADMIN, UserRole.RESPONDER])
    ),
):
    """Creates a new incident record and initializes the version counter to 1."""
    await ensure_assignee_exists(db, incident_in.assignee_id)

    incident = Incident(
        title=incident_in.title,
        description=incident_in.description,
        service_name=incident_in.service_name,
        severity=incident_in.severity,
        assignee_id=incident_in.assignee_id,
        reporter_id=current_user.id,
        status=IncidentStatus.OPEN,
        version=1,

    )
    db.add(incident)
    await db.flush()

    await record_audit_log(
        db=db,
        actor_id=current_user.id,
        action="INCIDENT_CREATED",
        entity_id=incident.id,
        changes=incident_in.model_dump(mode="json"),
    )
    await db.commit()
    await db.refresh(incident)
    return incident

@router.get("/", response_model=list[IncidentResponse])
async def list_incidents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service_name: str | None = Query(None, description="Filter by service name"),
    incident_status: IncidentStatus | None = Query(
        None, alias="status", description="Filter by status"
    ),
    severity: IncidentSeverity | None = Query(None, description="Filter by severity"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100)
):
    """Lists incidents with pagination and optional field-based filtering."""
    filters = [
        Incident.service_name == service_name if service_name else None,
        Incident.status == incident_status if incident_status else None,
        Incident.severity == severity if severity else None,
    ]

    stmt = (
        select(Incident)
        .where(*[f for f in filters if f is not None])
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves a single incident by ID."""
    return await get_incident_or_404(db, incident_id)

@router.patch("/{incident_id}", response_model=IncidentResponse)
async def update_incident(
    incident_id: uuid.UUID,
    incident_in: IncidentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        RequireRole([UserRole.ADMIN, UserRole.RESPONDER])
    ),
):
    """Updates an existing incident using conditional updates for Optimistic Concurrency Control."""
    update_data = incident_in.model_dump(exclude_unset=True, exclude={"version"})

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided to update.",
        )

    if update_data.get("status") == IncidentStatus.RESOLVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use POST /incidents/{incident_id}/resolve to resolve an incident.",
        )

    if "assignee_id" in update_data:
        await ensure_assignee_exists(db, update_data["assignee_id"])

    update_data["updated_at"] = datetime.now(timezone.utc)

    await apply_optimistic_update(db, incident_id, incident_in.version, update_data)

    await record_audit_log(
        db=db,
        actor_id=current_user.id,
        action="INCIDENT_UPDATED",
        entity_id=incident_id,
        changes=incident_in.model_dump(mode="json", exclude_unset=True, exclude={"version"}),
    )

    await db.commit()
    return await get_incident_or_404(db, incident_id)


@router.post("/{incident_id}/resolve", response_model=IncidentResponse)
async def resolve_incident(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        RequireRole([UserRole.ADMIN, UserRole.RESPONDER])
    ),
):
    """Transitions incident to RESOLVED and calculates MTTR in seconds."""
    incident = await get_incident_or_404(db, incident_id)

    if incident.status == IncidentStatus.RESOLVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incident is already marked as RESOLVED.",
        )

    now = datetime.now(timezone.utc)
    mttr_seconds = (now - incident.created_at).total_seconds()

    await apply_optimistic_update(
        db,
        incident_id,
        incident.version,
        {"status": IncidentStatus.RESOLVED, "resolved_at": now},
    )

    await record_audit_log(
        db=db,
        actor_id=current_user.id,
        action="INCIDENT_RESOLVED",
        entity_id=incident.id,
        changes={
            "status": IncidentStatus.RESOLVED.value,
            "resolved_at": now.isoformat(),
            "mttr_seconds": mttr_seconds,
        },
    )

    await db.commit()
    return await get_incident_or_404(db, incident_id)

