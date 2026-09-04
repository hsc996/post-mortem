import uuid

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import RequireRole, get_current_user, oauth2_scheme
from src.core.database import get_db
from src.core.rate_limit import limiter
from src.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    get_password_hash,
    revoke_token,
    verify_password,
)
from src.models.user import User, UserRole
from src.schemas.auth import RoleUpdate, Token, UserCreate, UserResponse, UserSummary
from src.services.audit import record_audit_log

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register_user(request: Request, user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == user_in.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists.",
        )

    # Self-registration always creates a read-only VIEWER account; an existing
    # admin must promote the user via PATCH /auth/users/{user_id}/role.
    user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        first_name=user_in.first_name,
        last_name=user_in.last_name,
        role=UserRole.VIEWER,
        phone=user_in.phone_number,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # Two concurrent registrations for the same email raced past the check above.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists.",
        )
    await db.refresh(user)
    return user


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    # Always run a bcrypt comparison, even when the user doesn't exist, so that
    # response timing doesn't leak whether an email is registered.
    password_valid = verify_password(
        form_data.password, user.hashed_password if user else DUMMY_PASSWORD_HASH
    )

    if not user or not password_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user account"
        )

    access_token = create_access_token(data={"sub": str(user.id), "role": user.role.value})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    try:
        await revoke_token(token, db)
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/me", response_model=UserResponse)
async def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/users", response_model=list[UserResponse] | list[UserSummary])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
):
    """
    Lists user accounts. Any authenticated user can call this — the incident
    feed and audit trail need it to resolve reporter/assignee/actor names —
    but only admins (who also drive the role-management screen) get email
    and role back; everyone else gets a name-only directory entry.
    """
    result = await db.execute(select(User).order_by(User.first_name).offset(skip).limit(limit))
    users = result.scalars().all()
    if current_user.role == UserRole.ADMIN:
        return users
    return [UserSummary.model_validate(user) for user in users]


@router.patch("/users/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    request: Request,
    user_id: uuid.UUID,
    role_in: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireRole([UserRole.ADMIN])),
):
    """Admin-only: grants or revokes admin/responder/viewer access for a user."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found.",
        )

    user.role = role_in.role
    await db.flush()

    await record_audit_log(
        db=db,
        actor_id=current_user.id,
        entity_type="user",
        action="USER_ROLE_CHANGED",
        entity_id=user.id,
        changes={"role": role_in.role.value},
        ip_address=request.client.host if request.client else None,
    )

    await db.commit()
    await db.refresh(user)
    return user