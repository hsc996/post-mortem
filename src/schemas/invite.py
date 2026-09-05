import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.models.user import UserRole


class InviteCreate(BaseModel):
    email: EmailStr = Field(..., max_length=255)
    role: UserRole


class InviteCreateResponse(BaseModel):
    """Returned once, at creation — carries the raw link so an admin can
    hand it to the invitee directly if email delivery isn't configured or fails."""

    id: uuid.UUID
    email: EmailStr
    role: UserRole
    expires_at: datetime
    invite_link: str


class InviteSummary(BaseModel):
    """One row of GET /auth/invites — the admin-facing pending/expired list."""

    id: uuid.UUID
    email: EmailStr
    role: UserRole
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime
    is_expired: bool
    is_accepted: bool

    model_config = ConfigDict(from_attributes=True)


class InvitePreview(BaseModel):
    """What GET /auth/invites/{token} returns to the (unauthenticated) invitee —
    just enough to render "you've been invited as VIEWER" before they accept."""

    email: EmailStr
    role: UserRole
    expires_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AcceptInviteRequest(BaseModel):
    password: str
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    phone_number: str | None = Field(default=None, max_length=50)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters long")
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password must not exceed 72 bytes")
        return v
