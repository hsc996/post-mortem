import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit import AuditLog


async def record_audit_log(
    db: AsyncSession,
    actor_id: uuid.UUID,
    entity_type: str,
    action: str,
    entity_id: uuid.UUID,
    changes: dict,
) -> None:
    log_entry = AuditLog(
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        changes=changes,
    )
    db.add(log_entry)
