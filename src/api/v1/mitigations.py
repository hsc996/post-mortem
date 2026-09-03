import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import RequireRole, get_current_user
from src.core.database import get_db
from src.models.incident import IncidentStatus
from src.models.mitigation import MitigationState
from src.models.user import User, UserRole
from src.schemas.mitigation import MitigationCreate, MitigationResponse
from src.services.audit import record_audit_log
from src.services.incidents import apply_optimistic_update, get_incident_or_404
from src.services.mitigations import get_mitigation_by_incident, get_mitigation_by_incident_or_404

router = APIRouter(prefix="/incidents/{incident_id}/mitigation", tags=["Mitigations"])


@router.post("/", response_model=MitigationResponse, status_code=status.HTTP_201_CREATED)
async def create_mitigation(
    incident_id: uuid.UUID,
    mitigation_in: MitigationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireRole([UserRole.ADMIN, UserRole.RESPONDER])),
):
    incident = await get_incident_or_404(db, incident_id)

    if incident.status == IncidentStatus.RESOLVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot apply a mitigation to a resolved incident.",
        )

    if await get_mitigation_by_incident(db, incident_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active mitigation already exists for this incident.",
        )

    mitigation = MitigationState(
        incident_id=incident_id,
        summary=mitigation_in.summary,
        ttl_minutes=mitigation_in.ttl_minutes,
        applied_at=datetime.now(timezone.utc),
        applied_by_id=current_user.id,
    )
    db.add(mitigation)

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active mitigation already exists for this incident.",
        )

    await apply_optimistic_update(
        db, incident_id, incident.version, {"status": IncidentStatus.MITIGATED}
    )

    await record_audit_log(
        db=db,
        actor_id=current_user.id,
        entity_type="mitigation",
        action="MITIGATION_CREATED",
        entity_id=mitigation.id,
        changes=mitigation_in.model_dump(mode="json"),
    )

    await db.commit()
    await db.refresh(mitigation)
    return mitigation


@router.get("/", response_model=MitigationResponse)
async def get_mitigation(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await get_mitigation_by_incident_or_404(db, incident_id)


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
async def clear_mitigation(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireRole([UserRole.ADMIN, UserRole.RESPONDER])),
):
    mitigation = await get_mitigation_by_incident_or_404(db, incident_id)
    incident = await get_incident_or_404(db, incident_id)

    if incident.status == IncidentStatus.MITIGATED:
        await apply_optimistic_update(
            db, incident.id, incident.version, {"status": IncidentStatus.OPEN}
        )

    mitigation_id = mitigation.id
    await db.delete(mitigation)

    await record_audit_log(
        db=db,
        actor_id=current_user.id,
        entity_type="mitigation",
        action="MITIGATION_DELETED",
        entity_id=mitigation_id,
        changes={"incident_id": str(incident_id)},
    )

    await db.commit()
    return None
