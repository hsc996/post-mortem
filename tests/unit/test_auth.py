import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from src.core.security import get_password_hash
from src.models.account import Account
from src.models.revoked_token import RevokedToken
from src.models.user import User, UserRole

LOGIN_URL = "/api/v1/auth/login"
LOGOUT_URL = "/api/v1/auth/logout"
ME_URL = "/api/v1/auth/me"
REGISTER_URL = "/api/v1/auth/register"

PASSWORD = "Sup3rSecret!"


def register_payload(**overrides) -> dict:
    payload = {
        "account_name": "Test Co",
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
    account = Account(name=f"Test Account {uuid.uuid4()}")
    db_session.add(account)
    await db_session.flush()

    user = User(
        account_id=account.id,
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
async def test_login_rate_limited_after_five_attempts(client, db_session):
    user = await create_user_with_password(db_session)

    for _ in range(5):
        response = await client.post(
            LOGIN_URL, data={"username": user.email, "password": "wrong-password"}
        )
        assert response.status_code == 401

    response = await client.post(
        LOGIN_URL, data={"username": user.email, "password": "wrong-password"}
    )
    assert response.status_code == 429


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
async def test_register_creates_admin_and_new_account(client):
    response = await client.post(REGISTER_URL, json=register_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]

    me_response = await client.get(ME_URL, headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me_response.status_code == 200
    me_body = me_response.json()
    assert me_body["role"] == "admin"
    assert me_body["account_name"] == "Test Co"


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_400(client):
    payload = register_payload()
    await client.post(REGISTER_URL, json=payload)

    response = await client.post(REGISTER_URL, json=payload)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_register_weak_password_returns_422(client):
    response = await client.post(REGISTER_URL, json=register_payload(password="short"))

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_rate_limited_after_five_attempts(client):
    for _ in range(5):
        response = await client.post(REGISTER_URL, json=register_payload())
        assert response.status_code == 201

    response = await client.post(REGISTER_URL, json=register_payload())
    assert response.status_code == 429


@pytest.mark.asyncio
async def test_two_registrations_are_fully_isolated_accounts(client, make_user, as_user):
    """The core tenancy assertion at the register boundary: two self-registered
    admins must never see each other's user directory."""
    register_response = await client.post(REGISTER_URL, json=register_payload(account_name="Other Co"))
    other_admin_id = (
        await client.get(
            ME_URL, headers={"Authorization": f"Bearer {register_response.json()['access_token']}"}
        )
    ).json()["id"]

    admin = await make_user(role=UserRole.ADMIN)
    as_user(admin)

    response = await client.get("/api/v1/auth/users")

    assert response.status_code == 200
    assert other_admin_id not in {row["id"] for row in response.json()}


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
async def test_logout_purges_expired_revoked_tokens(client, db_session):
    stale = RevokedToken(
        jti=str(uuid.uuid4()),
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(stale)
    await db_session.commit()

    user = await create_user_with_password(db_session)
    login_response = await client.post(
        LOGIN_URL, data={"username": user.email, "password": PASSWORD}
    )
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    logout_response = await client.post(LOGOUT_URL, headers=headers)
    assert logout_response.status_code == 204

    result = await db_session.execute(
        select(RevokedToken.jti).where(RevokedToken.jti == stale.jti)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_logout_invalid_token_returns_401(client):
    response = await client.post(
        LOGOUT_URL, headers={"Authorization": "Bearer not-a-real-token"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_users_as_admin_returns_full_fields(client, make_user, as_user):
    admin = await make_user(role=UserRole.ADMIN)
    other = await make_user(role=UserRole.RESPONDER, first_name="Jing", last_name="Meng")
    as_user(admin)

    response = await client.get("/api/v1/auth/users")

    assert response.status_code == 200
    by_id = {row["id"]: row for row in response.json()}
    assert set(by_id[str(other.id)].keys()) == {
        "id", "email", "first_name", "last_name", "role", "is_active", "account_name",
    }
    assert by_id[str(other.id)]["email"] == other.email
    assert by_id[str(other.id)]["role"] == "responder"


@pytest.mark.asyncio
async def test_list_users_as_non_admin_omits_email_and_role(client, make_user, as_user):
    viewer = await make_user(role=UserRole.VIEWER)
    other = await make_user(role=UserRole.ADMIN, first_name="Rafael", last_name="Okafor")
    as_user(viewer)

    response = await client.get("/api/v1/auth/users")

    assert response.status_code == 200
    by_id = {row["id"]: row for row in response.json()}
    assert set(by_id[str(other.id)].keys()) == {"id", "first_name", "last_name"}
    assert by_id[str(other.id)]["first_name"] == "Rafael"


@pytest.mark.asyncio
async def test_list_users_without_token_returns_401(client):
    response = await client.get("/api/v1/auth/users")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_users_respects_limit(client, make_user, as_user):
    admin = await make_user(role=UserRole.ADMIN)
    for _ in range(3):
        await make_user(role=UserRole.VIEWER)
    as_user(admin)

    response = await client.get("/api/v1/auth/users", params={"limit": 2})

    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_update_user_role_as_admin_succeeds(client, make_user, as_user):
    admin = await make_user(role=UserRole.ADMIN)
    target = await make_user(role=UserRole.RESPONDER)
    as_user(admin)

    response = await client.patch(
        f"/api/v1/auth/users/{target.id}/role", json={"role": "admin"}
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_update_user_role_as_non_admin_forbidden(client, make_user, as_user):
    responder = await make_user(role=UserRole.RESPONDER)
    target = await make_user(role=UserRole.RESPONDER)
    as_user(responder)

    response = await client.patch(
        f"/api/v1/auth/users/{target.id}/role", json={"role": "admin"}
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_user_role_unknown_user_returns_404(client, make_user, as_user):
    admin = await make_user(role=UserRole.ADMIN)
    as_user(admin)

    response = await client.patch(
        f"/api/v1/auth/users/{uuid.uuid4()}/role", json={"role": "admin"}
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_user_role_cross_account_returns_404(client, make_user, make_account, as_user):
    """An admin in one account must not be able to touch a user in another
    account, even by a correctly-guessed UUID — this was a real privilege-
    escalation hole before every query got account-scoped."""
    other_account = await make_account(name="Other Co")
    target = await make_user(role=UserRole.RESPONDER, account=other_account)
    admin = await make_user(role=UserRole.ADMIN)
    as_user(admin)

    response = await client.patch(
        f"/api/v1/auth/users/{target.id}/role", json={"role": "admin"}
    )

    assert response.status_code == 404
