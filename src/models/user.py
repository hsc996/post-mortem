import enum
import uuid
from sqlalchemy import Enum as SQLEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import Base, TimestampMixin

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    RESPONDER = "responder"
    VIEWER = "viewer"

class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole), default=UserRole.RESPONDER, nullable=False
    )
    phone: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # FK mapping
    account: Mapped["Account"] = relationship("Account", lazy="selectin")
    reported_incidents: Mapped[list["Incident"]] = relationship(
        "Incident", foreign_keys="Incident.reporter_id", back_populates="reporter"
    )
    assigned_incidents: Mapped[list["Incident"]] = relationship(
        "Incident", foreign_keys="Incident.assignee_id", back_populates="assignee"
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def account_name(self) -> str:
        return self.account.name
