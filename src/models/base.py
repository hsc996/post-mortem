from datetime import datetime, timezone
from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

class Base(DeclarativeBase):
    pass

class TZDateTime(TypeDecorator):
    """DateTime(timezone=True) that guarantees a UTC-aware value on read, even
    on backends that silently drop tzinfo on round-trip. Postgres already preserves tzinfo, so this is a no-op there."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value

class TimestampMixin:
    """Mixin to add standard created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        TZDateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )