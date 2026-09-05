import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit import AuditLog

async def record_audit_log(
    db: AsyncSession,
    actor_id: uuid.UUID,
    account_id: uuid.UUID,
    entity_type: str,
    action: str,
    entity_id: uuid.UUID,
    changes: dict,
    incident_id: uuid.UUID | None = None,
    ip_address: str | None = None,
) -> None:
    log_entry = AuditLog(
        actor_id=actor_id,
        account_id=account_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        changes=changes,
        incident_id=incident_id,
        ip_address=ip_address,
    )
    db.add(log_entry)


async def list_audit_log_for_incident(
    db: AsyncSession, incident_id: uuid.UUID, account_id: uuid.UUID
) -> list[AuditLog]:
    """Returns the full audit timeline for an incident, oldest first."""
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.incident_id == incident_id, AuditLog.account_id == account_id)
        .order_by(AuditLog.created_at)
    )
    return list(result.scalars().all())
