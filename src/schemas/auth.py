import uuid
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from src.models.user import UserRole


class UserCreate(BaseModel):
    email: EmailStr = Field(..., max_length=255)
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


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    first_name: str
    last_name: str
    role: UserRole
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class UserSummary(BaseModel):
    """Name-only directory entry — what GET /auth/users returns to non-admins,
    who need it purely to resolve reporter/assignee/actor names in the UI and
    have no legitimate reason to see colleagues' emails or roles."""

    id: uuid.UUID
    first_name: str
    last_name: str

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RoleUpdate(BaseModel):
    role: UserRole


class TokenData(BaseModel):
    sub: str | None = None