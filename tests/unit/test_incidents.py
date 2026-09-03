import uuid

import pytest
from sqlalchemy import select

from src.models.audit import AuditLog
from src.models.incident import Incident, IncidentStatus
from src.models.user import UserRole

INCIDENTS_URL = "/api/v1/incidents/"


def incident_payload(**overrides) -> dict:
    payload = {
        "title": "API Gateway High Latency",
        "description": "P99 response time spiked to 2.5s",
        "service_name": "api-gateway",
        "severity": "high",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_create_incident_as_responder_succeeds(client, make_user, as_user):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)

    response = await client.post(INCIDENTS_URL, json=incident_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "open"
    assert body["version"] == 1
    assert body["reporter_id"] == str(responder.id)


@pytest.mark.asyncio
async def test_create_incident_as_viewer_forbidden(client, make_user, as_user):
    viewer = await make_user(role=UserRole.VIEWER)
    as_user(viewer)

    response = await client.post(INCIDENTS_URL, json=incident_payload())

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_incident_with_unknown_assignee_returns_400(client, make_user, as_user):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)

    response = await client.post(
        INCIDENTS_URL, json=incident_payload(assignee_id=str(uuid.uuid4()))
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_incident_records_audit_log(client, make_user, as_user, db_session):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)

    response = await client.post(INCIDENTS_URL, json=incident_payload())
    incident_id = uuid.UUID(response.json()["id"])

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.entity_id == incident_id)
    )
    log_entry = result.scalar_one()
    assert log_entry.action == "INCIDENT_CREATED"
    assert log_entry.actor_id == responder.id


@pytest.mark.asyncio
async def test_list_incidents_filters_by_service_name(client, make_user, as_user):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    await client.post(INCIDENTS_URL, json=incident_payload(service_name="api-gateway"))
    await client.post(INCIDENTS_URL, json=incident_payload(service_name="billing-worker"))

    response = await client.get(INCIDENTS_URL, params={"service_name": "billing-worker"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["service_name"] == "billing-worker"


@pytest.mark.asyncio
async def test_list_incidents_respects_limit(client, make_user, as_user):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    for _ in range(3):
        await client.post(INCIDENTS_URL, json=incident_payload())

    response = await client.get(INCIDENTS_URL, params={"limit": 2})

    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_get_incident_not_found_returns_404(client, make_user, as_user):
    viewer = await make_user(role=UserRole.VIEWER)
    as_user(viewer)

    response = await client.get(f"{INCIDENTS_URL}{uuid.uuid4()}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_incident_requires_authentication(client):
    response = await client.get(f"{INCIDENTS_URL}{uuid.uuid4()}")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_incident_success_bumps_version(client, make_user, as_user):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    created = (await client.post(INCIDENTS_URL, json=incident_payload())).json()

    response = await client.patch(
        f"{INCIDENTS_URL}{created['id']}",
        json={"version": created["version"], "severity": "critical"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == created["version"] + 1
    assert body["severity"] == "critical"


@pytest.mark.asyncio
async def test_update_incident_stale_version_returns_409(client, make_user, as_user):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    created = (await client.post(INCIDENTS_URL, json=incident_payload())).json()
    await client.patch(
        f"{INCIDENTS_URL}{created['id']}",
        json={"version": created["version"], "severity": "critical"},
    )

    response = await client.patch(
        f"{INCIDENTS_URL}{created['id']}",
        json={"version": created["version"], "severity": "low"},
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_update_incident_no_fields_returns_400(client, make_user, as_user):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    created = (await client.post(INCIDENTS_URL, json=incident_payload())).json()

    response = await client.patch(
        f"{INCIDENTS_URL}{created['id']}", json={"version": created["version"]}
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_update_incident_cannot_set_status_resolved_directly(client, make_user, as_user):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    created = (await client.post(INCIDENTS_URL, json=incident_payload())).json()

    response = await client.patch(
        f"{INCIDENTS_URL}{created['id']}",
        json={"version": created["version"], "status": "resolved"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_update_incident_with_unknown_assignee_returns_400(client, make_user, as_user):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    created = (await client.post(INCIDENTS_URL, json=incident_payload())).json()

    response = await client.patch(
        f"{INCIDENTS_URL}{created['id']}",
        json={"version": created["version"], "assignee_id": str(uuid.uuid4())},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_resolve_incident_success_sets_resolved_at_and_logs_mttr(
    client, make_user, as_user, db_session
):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    created = (await client.post(INCIDENTS_URL, json=incident_payload())).json()

    response = await client.post(f"{INCIDENTS_URL}{created['id']}/resolve")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resolved"
    assert body["resolved_at"] is not None
    assert body["version"] == created["version"] + 1

    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.entity_id == uuid.UUID(created["id"]),
            AuditLog.action == "INCIDENT_RESOLVED",
        )
    )
    log_entry = result.scalar_one()
    assert "mttr_seconds" in log_entry.changes


@pytest.mark.asyncio
async def test_resolve_incident_already_resolved_returns_400(client, make_user, as_user):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    created = (await client.post(INCIDENTS_URL, json=incident_payload())).json()
    await client.post(f"{INCIDENTS_URL}{created['id']}/resolve")

    response = await client.post(f"{INCIDENTS_URL}{created['id']}/resolve")

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_resolve_incident_as_viewer_forbidden(client, make_user, as_user):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    created = (await client.post(INCIDENTS_URL, json=incident_payload())).json()

    viewer = await make_user(role=UserRole.VIEWER)
    as_user(viewer)
    response = await client.post(f"{INCIDENTS_URL}{created['id']}/resolve")

    assert response.status_code == 403
