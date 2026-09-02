import enum
import uuid
from datetime import datetime
from sqlalchemy import Enum as SQLEnum, String, DateTime, Integer, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import Base, TimestampMixin

class IncidentSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class IncidentStatus(str, enum.Enum):
    OPEN = "open"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"

class Incident(Base, TimestampMixin):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    service_name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    severity: Mapped[IncidentSeverity] = mapped_column(
        SQLEnum(IncidentSeverity), default=IncidentSeverity.MEDIUM, nullable=False
    )
    status: Mapped[IncidentStatus] = mapped_column(
        SQLEnum(IncidentStatus), default=IncidentStatus.OPEN, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # FK mapping
    reporter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    reporter: Mapped["User"] = relationship(
        "User", foreign_keys=[reporter_id], back_populates="reported_incidents"
    )
    assignee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    assignee: Mapped["User | None"] = relationship(
        "User", foreign_keys=[assignee_id], back_populates="assigned_incidents"
    )
    mitigation_state: Mapped["MitigationState | None"] = relationship(
        back_populates="incident", uselist=False, cascade="all, delete-orphan"
    )