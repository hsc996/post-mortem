import uuid
from datetime import UTC, datetime

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, TZDateTime
from src.models.user import UserRole


class Invite(Base, TimestampMixin):
    __tablename__ = "invites"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole, name="userrole"), nullable=False)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    invited_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    invited_by: Mapped["User"] = relationship("User")

    @property
    def is_expired(self) -> bool:
        """Read-time evaluation, same discipline as MitigationState.is_expired — never trust a cached flag."""
        return datetime.now(UTC) >= self.expires_at

    @property
    def is_accepted(self) -> bool:
        return self.accepted_at is not None
