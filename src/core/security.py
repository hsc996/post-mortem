import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.revoked_token import RevokedToken

ALGORITHM = "HS256"
MAX_PASSWORD_BYTES = 72
DUMMY_PASSWORD_HASH = bcrypt.hashpw(b"dummy-password-for-timing", bcrypt.gensalt()).decode("utf-8")


def get_password_hash(password: str) -> str:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must not exceed {MAX_PASSWORD_BYTES} bytes")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_bytes = plain_password.encode("utf-8")
    if len(password_bytes) > MAX_PASSWORD_BYTES:
        return False
    return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": now, "jti": str(uuid.uuid4())})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


async def decode_access_token(token: str, db: AsyncSession) -> dict:
    """Decode and validate a token, raising jwt.InvalidTokenError (or a subclass,
    e.g. jwt.ExpiredSignatureError) if it is malformed, expired, or revoked."""
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    jti = payload.get("jti")
    if jti is None:
        raise jwt.InvalidTokenError("Token missing jti claim")

    result = await db.execute(select(RevokedToken.jti).where(RevokedToken.jti == jti))
    if result.scalar_one_or_none() is not None:
        raise jwt.InvalidTokenError("Token has been revoked")

    return payload


async def revoke_token(token: str, db: AsyncSession) -> None:
    """Add a token's jti to the denylist so it can no longer be used, even
    though it remains cryptographically valid until it expires."""
    payload = jwt.decode(
        token, settings.SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False}
    )
    jti = payload.get("jti")
    exp_claim = payload.get("exp")
    if not jti:
        raise jwt.InvalidTokenError("Token missing jti claim")
    if not exp_claim:
        raise jwt.InvalidTokenError("Token missing exp claim")

    expires_at = datetime.fromtimestamp(exp_claim, tz=timezone.utc)

    # Opportunistically purge tokens that have already expired — an expired jti
    # is worthless to keep denylisted since decode_access_token would reject an
    # expired token on signature/exp verification before ever checking this
    # table. This keeps the table bounded without needing a separate scheduled job.
    await db.execute(delete(RevokedToken).where(RevokedToken.expires_at < datetime.now(timezone.utc)))

    stmt = (
        pg_insert(RevokedToken)
        .values(jti=jti, expires_at=expires_at)
        .on_conflict_do_nothing(index_elements=["jti"])
    )
    await db.execute(stmt)
    await db.commit()
