import uuid

import pytest

from src.core.security import get_password_hash
from src.models.user import User, UserRole

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
LOGOUT_URL = "/api/v1/auth/logout"
ME_URL = "/api/v1/auth/me"

PASSWORD = "Sup3rSecret!"


def register_payload(**overrides) -> dict:
    payload = {
        "email": f"{uuid.uuid4()}@pulseguard.io",
        "password": PASSWORD,
        "first_name": "Alex",
        "last_name": "Rivera",
    }
    payload.update(overrides)
    return payload


async def create_user_with_password(
    db_session, password: str = PASSWORD, role: UserRole = UserRole.RESPONDER, is_active: bool = True
) -> User:
    user = User(
        email=f"{uuid.uuid4()}@pulseguard.io",
        hashed_password=get_password_hash(password),
        first_name="Test",
        last_name="User",
        role=role,
        is_active=is_active,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_register_user_success(client):
    response = await client.post(REGISTER_URL, json=register_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "responder"
    assert body["is_active"] is True
    assert "password" not in body
    assert "hashed_password" not in body


@pytest.mark.asyncio
async def test_register_user_duplicate_email_returns_400(client):
    payload = register_payload()
    await client.post(REGISTER_URL, json=payload)

    response = await client.post(REGISTER_URL, json=payload)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_register_user_weak_password_returns_422(client):
    response = await client.post(REGISTER_URL, json=register_payload(password="short"))

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_success_returns_token(client, db_session):
    user = await create_user_with_password(db_session)

    response = await client.post(
        LOGIN_URL, data={"username": user.email, "password": PASSWORD}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client, db_session):
    user = await create_user_with_password(db_session)

    response = await client.post(
        LOGIN_URL, data={"username": user.email, "password": "wrong-password"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email_returns_401(client):
    response = await client.post(
        LOGIN_URL, data={"username": "nobody@pulseguard.io", "password": PASSWORD}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_inactive_user_returns_400(client, db_session):
    user = await create_user_with_password(db_session, is_active=False)

    response = await client.post(
        LOGIN_URL, data={"username": user.email, "password": PASSWORD}
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_me_returns_current_user(client, make_user, as_user):
    user = await make_user(role=UserRole.ADMIN)
    as_user(user)

    response = await client.get(ME_URL)

    assert response.status_code == 200
    assert response.json()["id"] == str(user.id)


@pytest.mark.asyncio
async def test_me_without_token_returns_401(client):
    response = await client.get(ME_URL)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_token(client, db_session):
    user = await create_user_with_password(db_session)
    login_response = await client.post(
        LOGIN_URL, data={"username": user.email, "password": PASSWORD}
    )
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    logout_response = await client.post(LOGOUT_URL, headers=headers)
    assert logout_response.status_code == 204

    me_response = await client.get(ME_URL, headers=headers)
    assert me_response.status_code == 401


@pytest.mark.asyncio
async def test_logout_invalid_token_returns_401(client):
    response = await client.post(
        LOGOUT_URL, headers={"Authorization": "Bearer not-a-real-token"}
    )

    assert response.status_code == 401
