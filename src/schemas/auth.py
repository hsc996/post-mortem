import uuid
from pydantic import BaseModel, EmailStr, ConfigDict
from src.models.user import UserRole


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