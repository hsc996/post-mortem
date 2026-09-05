import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.models.audit import AuditLog
from src.models.user import UserRole

AUDIT_URL = "/api/v1/audit-logs/"


async def make_audit_log(db_session, account_id: uuid.UUID, **overrides) -> AuditLog:
    log = AuditLog(
        account_id=account_id,
        actor_id=overrides.get("actor_id", uuid.uuid4()),
        entity_type=overrides.get("entity_type", "incident"),
        entity_id=overrides.get("entity_id", uuid.uuid4()),
        action=overrides.get("action", "INCIDENT_CREATED"),
        changes=overrides.get("changes", {"status": "open"}),
        incident_id=overrides.get("incident_id"),
        ip_address=overrides.get("ip_address"),
        created_at=overrides.get("created_at", datetime.now(timezone.utc)),
    )
    db_session.add(log)
    await db_session.commit()
    await db_session.refresh(log)
    return log


@pytest.mark.asyncio
async def test_list_audit_logs_as_admin_succeeds(client, make_user, as_user, db_session):
    admin = await make_user(role=UserRole.ADMIN)
    as_user(admin)
    await make_audit_log(db_session, admin.account_id)
    await make_audit_log(db_session, admin.account_id)

    response = await client.get(AUDIT_URL)

    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_list_audit_logs_as_responder_succeeds(client, make_user, as_user, db_session):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    await make_audit_log(db_session, responder.account_id)

    response = await client.get(AUDIT_URL)

    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_list_audit_logs_as_viewer_forbidden(client, make_user, as_user):
    viewer = await make_user(role=UserRole.VIEWER)
    as_user(viewer)

    response = await client.get(AUDIT_URL)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_audit_logs_requires_authentication(client):
    response = await client.get(AUDIT_URL)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_audit_logs_scoped_to_account(client, make_user, make_account, as_user, db_session):
    other_account = await make_account(name="Other Co")
    other_admin = await make_user(role=UserRole.ADMIN, account=other_account)
    await make_audit_log(db_session, other_admin.account_id)

    admin = await make_user(role=UserRole.ADMIN)
    await make_audit_log(db_session, admin.account_id)
    as_user(admin)

    response = await client.get(AUDIT_URL)

    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_list_audit_logs_filters_by_entity_type(client, make_user, as_user, db_session):
    admin = await make_user(role=UserRole.ADMIN)
    as_user(admin)
    await make_audit_log(db_session, admin.account_id, entity_type="incident")
    await make_audit_log(db_session, admin.account_id, entity_type="mitigation")

    response = await client.get(AUDIT_URL, params={"entity_type": "mitigation"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["entity_type"] == "mitigation"


@pytest.mark.asyncio
async def test_list_audit_logs_filters_by_entity_id(client, make_user, as_user, db_session):
    admin = await make_user(role=UserRole.ADMIN)
    as_user(admin)
    target_id = uuid.uuid4()
    await make_audit_log(db_session, admin.account_id, entity_id=target_id)
    await make_audit_log(db_session, admin.account_id, entity_id=uuid.uuid4())

    response = await client.get(AUDIT_URL, params={"entity_id": str(target_id)})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["entity_id"] == str(target_id)


@pytest.mark.asyncio
async def test_list_audit_logs_filters_by_actor_id(client, make_user, as_user, db_session):
    admin = await make_user(role=UserRole.ADMIN)
    as_user(admin)
    actor_id = uuid.uuid4()
    await make_audit_log(db_session, admin.account_id, actor_id=actor_id)
    await make_audit_log(db_session, admin.account_id, actor_id=uuid.uuid4())

    response = await client.get(AUDIT_URL, params={"actor_id": str(actor_id)})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["actor_id"] == str(actor_id)


@pytest.mark.asyncio
async def test_list_audit_logs_orders_newest_first(client, make_user, as_user, db_session):
    admin = await make_user(role=UserRole.ADMIN)
    as_user(admin)
    older = await make_audit_log(
        db_session, admin.account_id, created_at=datetime.now(timezone.utc) - timedelta(minutes=10)
    )
    newer = await make_audit_log(db_session, admin.account_id, created_at=datetime.now(timezone.utc))

    response = await client.get(AUDIT_URL)

    assert response.status_code == 200
    ids = [entry["id"] for entry in response.json()]
    assert ids == [str(newer.id), str(older.id)]


@pytest.mark.asyncio
async def test_list_audit_logs_respects_pagination(client, make_user, as_user, db_session):
    admin = await make_user(role=UserRole.ADMIN)
    as_user(admin)
    for _ in range(3):
        await make_audit_log(db_session, admin.account_id)

    response = await client.get(AUDIT_URL, params={"skip": 1, "limit": 1})

    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_get_entity_audit_trail_as_responder_can_read(client, make_user, as_user, db_session):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    entity_id = uuid.uuid4()
    await make_audit_log(db_session, responder.account_id, entity_id=entity_id)

    response = await client.get(f"{AUDIT_URL}entity/{entity_id}")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["entity_id"] == str(entity_id)


@pytest.mark.asyncio
async def test_get_entity_audit_trail_as_viewer_forbidden(client, make_user, as_user, db_session):
    viewer = await make_user(role=UserRole.VIEWER)
    as_user(viewer)
    entity_id = uuid.uuid4()
    await make_audit_log(db_session, viewer.account_id, entity_id=entity_id)

    response = await client.get(f"{AUDIT_URL}entity/{entity_id}")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_entity_audit_trail_excludes_other_entities(client, make_user, as_user, db_session):
    admin = await make_user(role=UserRole.ADMIN)
    as_user(admin)
    entity_id = uuid.uuid4()
    await make_audit_log(db_session, admin.account_id, entity_id=entity_id)
    await make_audit_log(db_session, admin.account_id, entity_id=uuid.uuid4())

    response = await client.get(f"{AUDIT_URL}entity/{entity_id}")

    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_get_entity_audit_trail_respects_pagination(client, make_user, as_user, db_session):
    admin = await make_user(role=UserRole.ADMIN)
    as_user(admin)
    entity_id = uuid.uuid4()
    for _ in range(3):
        await make_audit_log(db_session, admin.account_id, entity_id=entity_id)

    response = await client.get(
        f"{AUDIT_URL}entity/{entity_id}", params={"skip": 1, "limit": 1}
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_entity_audit_trail_scoped_to_account(client, make_user, make_account, as_user, db_session):
    entity_id = uuid.uuid4()
    other_account = await make_account(name="Other Co")
    other_admin = await make_user(role=UserRole.ADMIN, account=other_account)
    await make_audit_log(db_session, other_admin.account_id, entity_id=entity_id)

    admin = await make_user(role=UserRole.ADMIN)
    await make_audit_log(db_session, admin.account_id, entity_id=entity_id)
    as_user(admin)

    response = await client.get(f"{AUDIT_URL}entity/{entity_id}")

    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_get_entity_audit_trail_requires_authentication(client):
    response = await client.get(f"{AUDIT_URL}entity/{uuid.uuid4()}")

    assert response.status_code == 401
