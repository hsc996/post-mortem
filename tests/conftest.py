import asyncio
import os
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-only-0000")

from src.api.deps import get_current_user
from src.core.database import get_db
from src.core.rate_limit import limiter
from src.main import app
from src.models.base import Base
from src.models.user import User, UserRole


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Clears slowapi's in-memory rate-limit counters before every test so
    tests that repeatedly hit rate-limited endpoints (login/register) don't
    bleed into each other."""
    limiter.reset()
    yield

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provides a transactional database session that resets after every test."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """An HTTP client for the app wired to the same transactional test session."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def make_user(db_session: AsyncSession):
    """Factory fixture for creating persisted users with a given role."""

    async def _make_user(role: UserRole = UserRole.RESPONDER, **overrides) -> User:
        user = User(
            email=overrides.get("email", f"{uuid.uuid4()}@pulseguard.io"),
            hashed_password="hashed_secret_123",
            first_name=overrides.get("first_name", "Test"),
            last_name=overrides.get("last_name", "User"),
            role=role,
            is_active=overrides.get("is_active", True),
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    return _make_user


@pytest.fixture
def as_user(client: AsyncClient):
    """Makes subsequent requests on `client` authenticate as the given user."""

    def _as_user(user: User) -> None:
        app.dependency_overrides[get_current_user] = lambda: user

    return _as_user