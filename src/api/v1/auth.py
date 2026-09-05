import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import RequireRole, get_current_user, oauth2_scheme
from src.config import settings
from src.core.database import get_db
from src.core.rate_limit import limiter
from src.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    get_password_hash,
    revoke_token,
    verify_password,
)
from src.models.invite import Invite
from src.models.user import User, UserRole
from src.schemas.auth import RoleUpdate, Token, UserResponse, UserSummary
from src.schemas.invite import (
    AcceptInviteRequest,
    InviteCreate,
    InviteCreateResponse,
    InvitePreview,
    InviteSummary,
)
from src.services.audit import record_audit_log
from src.services.email import send_invite_email

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/invites", response_model=InviteCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_invite(
    invite_in: InviteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireRole([UserRole.ADMIN])),
):
    """Admin-only: invites a new user by email with a pre-set role. Self-registration
    doesn't exist — this is the only way a new account gets created."""
    result = await db.execute(select(User).where(User.email == invite_in.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists.",
        )

    invite = Invite(
        email=invite_in.email,
        role=invite_in.role,
        token=secrets.token_urlsafe(32),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.INVITE_TTL_DAYS),
        invited_by_id=current_user.id,
    )
    db.add(invite)
    await db.flush()

    invite_link = f"{settings.FRONTEND_URL}/invite/{invite.token}"
    send_invite_email(invite.email, invite.role, invite_link)

    await db.commit()
    await db.refresh(invite)
    return InviteCreateResponse(
        id=invite.id,
        email=invite.email,
        role=invite.role,
        expires_at=invite.expires_at,
        invite_link=invite_link,
    )


@router.get("/invites", response_model=list[InviteSummary])
async def list_invites(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireRole([UserRole.ADMIN])),
):
    """Admin-only: pending and expired invites, most recent first."""
    result = await db.execute(select(Invite).order_by(Invite.created_at.desc()))
    return result.scalars().all()


@router.get("/invites/{token}", response_model=InvitePreview)
async def preview_invite(token: str, db: AsyncSession = Depends(get_db)):
    """Public: lets the invite-accept screen show who/what the invite is for
    before the invitee sets a password."""
    result = await db.execute(select(Invite).where(Invite.token == token))
    invite = result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found.")
    if invite.is_accepted:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invite already accepted.")
    if invite.is_expired:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Invite has expired.")
    return invite


@router.post("/invites/{token}/accept", response_model=Token, status_code=status.HTTP_201_CREATED)
async def accept_invite(
    token: str, accept_in: AcceptInviteRequest, db: AsyncSession = Depends(get_db)
):
    """Public: creates the real account with the invite's pre-set role and
    signs the new user in immediately, same as a fresh login would."""
    result = await db.execute(select(Invite).where(Invite.token == token))
    invite = result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found.")
    if invite.is_accepted:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invite already accepted.")
    if invite.is_expired:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Invite has expired.")

    user = User(
        email=invite.email,
        hashed_password=get_password_hash(accept_in.password),
        first_name=accept_in.first_name,
        last_name=accept_in.last_name,
        role=invite.role,
        phone=accept_in.phone_number,
    )
    db.add(user)
    invite.accepted_at = datetime.now(timezone.utc)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists.",
        )
    await db.refresh(user)

    access_token = create_access_token(data={"sub": str(user.id), "role": user.role.value})
    return {"access_token": access_token, "token_type": "bearer"}


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