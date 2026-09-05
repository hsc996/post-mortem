import uuid
from datetime import datetime, timezone
from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import Base, TimestampMixin, TZDateTime

class MitigationState(Base, TimestampMixin):
    __tablename__ = "mitigation_state"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    ttl_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    applied_at: Mapped[datetime] = mapped_column(
        TZDateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    applied_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # FK mapping
    applied_by: Mapped["User"] = relationship("User")
    incident: Mapped["Incident"] = relationship(back_populates="mitigation_state")

    @property
    def is_expired(self) -> bool:
        """Read-time evaluation to check if mitigation TTL has elapsed."""
        now = datetime.now(timezone.utc)
        elapsed = (now - self.applied_at).total_seconds() / 60
        return elapsed >= self.ttl_minutes

