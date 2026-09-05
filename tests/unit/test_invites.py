import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.models.invite import Invite
from src.models.user import UserRole

INVITES_URL = "/api/v1/auth/invites"
ME_URL = "/api/v1/auth/me"

PASSWORD = "Sup3rSecret!"


def accept_payload(**overrides) -> dict:
    payload = {
        "password": PASSWORD,
        "first_name": "Alex",
        "last_name": "Rivera",
    }
    payload.update(overrides)
    return payload


async def create_invite(
    db_session,
    email: str | None = None,
    role: UserRole = UserRole.VIEWER,
    invited_by_id: uuid.UUID | None = None,
    expires_at: datetime | None = None,
    accepted_at: datetime | None = None,
) -> Invite:
    invite = Invite(
        email=email or f"{uuid.uuid4()}@pulseguard.io",
        role=role,
        token=uuid.uuid4().hex,
        expires_at=expires_at or (datetime.now(timezone.utc) + timedelta(days=7)),
        accepted_at=accepted_at,
        invited_by_id=invited_by_id,
    )
    db_session.add(invite)
    await db_session.commit()
    await db_session.refresh(invite)
    return invite


@pytest.mark.asyncio
async def test_create_invite_as_admin_returns_link(client, make_user, as_user):
    admin = await make_user(role=UserRole.ADMIN)
    as_user(admin)

    response = await client.post(
        INVITES_URL, json={"email": "newbie@pulseguard.io", "role": "responder"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "newbie@pulseguard.io"
    assert body["role"] == "responder"
    assert "/invite/" in body["invite_link"]
    assert "token" not in body


@pytest.mark.asyncio
async def test_create_invite_as_non_admin_forbidden(client, make_user, as_user):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)

    response = await client.post(
        INVITES_URL, json={"email": "newbie@pulseguard.io", "role": "responder"}
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_invite_existing_email_returns_400(client, make_user, as_user):
    admin = await make_user(role=UserRole.ADMIN)
    existing = await make_user(role=UserRole.VIEWER)
    as_user(admin)

    response = await client.post(
        INVITES_URL, json={"email": existing.email, "role": "viewer"}
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_list_invites_as_admin(client, make_user, as_user, db_session):
    admin = await make_user(role=UserRole.ADMIN)
    await create_invite(db_session, invited_by_id=admin.id)
    as_user(admin)

    response = await client.get(INVITES_URL)

    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_list_invites_as_non_admin_forbidden(client, make_user, as_user):
    viewer = await make_user(role=UserRole.VIEWER)
    as_user(viewer)

    response = await client.get(INVITES_URL)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_preview_invite_valid_token(client, make_user, db_session):
    admin = await make_user(role=UserRole.ADMIN)
    invite = await create_invite(db_session, role=UserRole.RESPONDER, invited_by_id=admin.id)

    response = await client.get(f"{INVITES_URL}/{invite.token}")

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == invite.email
    assert body["role"] == "responder"


@pytest.mark.asyncio
async def test_preview_invite_unknown_token_returns_404(client):
    response = await client.get(f"{INVITES_URL}/not-a-real-token")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_preview_invite_expired_returns_410(client, make_user, db_session):
    admin = await make_user(role=UserRole.ADMIN)
    invite = await create_invite(
        db_session,
        invited_by_id=admin.id,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )

    response = await client.get(f"{INVITES_URL}/{invite.token}")

    assert response.status_code == 410


@pytest.mark.asyncio
async def test_preview_invite_already_accepted_returns_409(client, make_user, db_session):
    admin = await make_user(role=UserRole.ADMIN)
    invite = await create_invite(
        db_session, invited_by_id=admin.id, accepted_at=datetime.now(timezone.utc)
    )

    response = await client.get(f"{INVITES_URL}/{invite.token}")

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_accept_invite_success_creates_user_and_signs_in(client, make_user, db_session):
    admin = await make_user(role=UserRole.ADMIN)
    invite = await create_invite(db_session, role=UserRole.RESPONDER, invited_by_id=admin.id)

    response = await client.post(
        f"{INVITES_URL}/{invite.token}/accept", json=accept_payload()
    )

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    token = body["access_token"]

    me_response = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 200
    me_body = me_response.json()
    assert me_body["email"] == invite.email
    assert me_body["role"] == "responder"


@pytest.mark.asyncio
async def test_accept_invite_unknown_token_returns_404(client):
    response = await client.post(
        f"{INVITES_URL}/not-a-real-token/accept", json=accept_payload()
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_accept_invite_expired_returns_410(client, make_user, db_session):
    admin = await make_user(role=UserRole.ADMIN)
    invite = await create_invite(
        db_session,
        invited_by_id=admin.id,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )

    response = await client.post(
        f"{INVITES_URL}/{invite.token}/accept", json=accept_payload()
    )

    assert response.status_code == 410


@pytest.mark.asyncio
async def test_accept_invite_already_accepted_returns_409(client, make_user, db_session):
    admin = await make_user(role=UserRole.ADMIN)
    invite = await create_invite(
        db_session, invited_by_id=admin.id, accepted_at=datetime.now(timezone.utc)
    )

    response = await client.post(
        f"{INVITES_URL}/{invite.token}/accept", json=accept_payload()
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_accept_invite_weak_password_returns_422(client, make_user, db_session):
    admin = await make_user(role=UserRole.ADMIN)
    invite = await create_invite(db_session, invited_by_id=admin.id)

    response = await client.post(
        f"{INVITES_URL}/{invite.token}/accept", json=accept_payload(password="short")
    )

    assert response.status_code == 422
