import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import RequireRole
from src.core.database import get_db
from src.models.audit import AuditLog
from src.models.user import User, UserRole
from src.schemas.audit import AuditLogResponse

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])

@router.get("/", response_model=list[AuditLogResponse])
async def list_audit_logs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        RequireRole([UserRole.ADMIN, UserRole.RESPONDER])
    ),
    entity_type: str | None = Query(
        None, description="Filter by entity type (e.g. 'incident', 'mitigation')"
    ),
    entity_id: uuid.UUID | None = Query(
        None, description="Filter by target entity UUID"
    ),
    actor_id: uuid.UUID | None = Query(
        None, description="Filter by user UUID who performed the action"
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    """
    Retrieves system audit logs with optional entity, actor, and pagination filters.
    Restricted to ADMIN and RESPONDER roles.
    """
    stmt = select(AuditLog)

    filters = [
        AuditLog.entity_type == entity_type if entity_type else None,
        AuditLog.entity_id == entity_id if entity_id else None,
        AuditLog.actor_id == actor_id if actor_id else None,
    ]

    stmt = stmt.where(*[f for f in filters if f is not None])
    stmt = stmt.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(stmt)
    return result.scalars().all()

@router.get("/entity/{entity_id}", response_model=list[AuditLogResponse])
async def get_entity_audit_trail(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        RequireRole([UserRole.ADMIN, UserRole.RESPONDER])
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    """
    Retrieves the complete historical audit trail for a specific entity (e.g. an incident).
    Restricted to ADMIN and RESPONDER roles, since entity_id isn't scoped to a
    particular entity_type and could otherwise expose audit trails (e.g. another
    user's role-change history) that a VIEWER shouldn't see.
    """
    stmt = (
        select(AuditLog)
        .where(AuditLog.entity_id == entity_id)
        .order_by(AuditLog.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(stmt)
    return result.scalars().all()