import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from src.models.audit import AuditLog
from src.models.mitigation import MitigationState
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


def mitigation_payload(**overrides) -> dict:
    payload = {
        "summary": "Rolled back to previous deploy",
        "ttl_minutes": 60,
    }
    payload.update(overrides)
    return payload


def mitigation_url(incident_id) -> str:
    return f"{INCIDENTS_URL}{incident_id}/mitigation/"


async def create_incident(client, **overrides) -> dict:
    response = await client.post(INCIDENTS_URL, json=incident_payload(**overrides))
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_create_mitigation_as_responder_succeeds(client, make_user, as_user):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    incident = await create_incident(client)

    response = await client.post(mitigation_url(incident["id"]), json=mitigation_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["incident_id"] == incident["id"]
    assert body["summary"] == "Rolled back to previous deploy"
    assert body["is_expired"] is False

    incident_after = (await client.get(f"{INCIDENTS_URL}{incident['id']}")).json()
    assert incident_after["status"] == "mitigated"
    assert incident_after["version"] == incident["version"] + 1


@pytest.mark.asyncio
async def test_create_mitigation_summary_too_long_returns_422(client, make_user, as_user):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    incident = await create_incident(client)

    response = await client.post(
        mitigation_url(incident["id"]), json=mitigation_payload(summary="x" * 2_001)
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_mitigation_as_viewer_forbidden(client, make_user, as_user):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    incident = await create_incident(client)

    viewer = await make_user(role=UserRole.VIEWER)
    as_user(viewer)
    response = await client.post(mitigation_url(incident["id"]), json=mitigation_payload())

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_mitigation_incident_not_found_returns_404(client, make_user, as_user):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)

    response = await client.post(mitigation_url(uuid.uuid4()), json=mitigation_payload())

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_mitigation_on_resolved_incident_returns_400(client, make_user, as_user):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    incident = await create_incident(client)
    await client.post(f"{INCIDENTS_URL}{incident['id']}/resolve")

    response = await client.post(mitigation_url(incident["id"]), json=mitigation_payload())

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_mitigation_duplicate_returns_409(client, make_user, as_user):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    incident = await create_incident(client)
    await client.post(mitigation_url(incident["id"]), json=mitigation_payload())

    response = await client.post(mitigation_url(incident["id"]), json=mitigation_payload())

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_mitigation_records_audit_log(client, make_user, as_user, db_session):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    incident = await create_incident(client)

    response = await client.post(mitigation_url(incident["id"]), json=mitigation_payload())
    mitigation_id = uuid.UUID(response.json()["id"])

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.entity_id == mitigation_id)
    )
    log_entry = result.scalar_one()
    assert log_entry.action == "MITIGATION_CREATED"
    assert log_entry.entity_type == "mitigation"
    assert log_entry.actor_id == responder.id


@pytest.mark.asyncio
async def test_get_mitigation_success(client, make_user, as_user):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    incident = await create_incident(client)
    created = (
        await client.post(mitigation_url(incident["id"]), json=mitigation_payload())
    ).json()

    response = await client.get(mitigation_url(incident["id"]))

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


@pytest.mark.asyncio
async def test_get_mitigation_not_found_returns_404(client, make_user, as_user):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    incident = await create_incident(client)

    response = await client.get(mitigation_url(incident["id"]))

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_mitigation_requires_authentication(client):
    response = await client.get(mitigation_url(uuid.uuid4()))

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_mitigation_expired_flag_reflects_ttl(client, make_user, as_user, db_session):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    incident = await create_incident(client)
    await client.post(
        mitigation_url(incident["id"]), json=mitigation_payload(ttl_minutes=1)
    )

    result = await db_session.execute(
        select(MitigationState).where(MitigationState.incident_id == uuid.UUID(incident["id"]))
    )
    mitigation = result.scalar_one()
    mitigation.applied_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    await db_session.commit()

    response = await client.get(mitigation_url(incident["id"]))

    assert response.status_code == 200
    assert response.json()["is_expired"] is True


@pytest.mark.asyncio
async def test_clear_mitigation_success_reverts_incident_status(client, make_user, as_user):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    incident = await create_incident(client)
    await client.post(mitigation_url(incident["id"]), json=mitigation_payload())

    response = await client.delete(mitigation_url(incident["id"]))

    assert response.status_code == 204

    incident_after = (await client.get(f"{INCIDENTS_URL}{incident['id']}")).json()
    assert incident_after["status"] == "open"
    assert incident_after["version"] == incident["version"] + 2

    get_response = await client.get(mitigation_url(incident["id"]))
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_clear_mitigation_records_audit_log(client, make_user, as_user, db_session):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    incident = await create_incident(client)
    created = (
        await client.post(mitigation_url(incident["id"]), json=mitigation_payload())
    ).json()

    await client.delete(mitigation_url(incident["id"]))

    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.entity_id == uuid.UUID(created["id"]),
            AuditLog.action == "MITIGATION_DELETED",
        )
    )
    log_entry = result.scalar_one()
    assert log_entry.entity_type == "mitigation"
    assert log_entry.changes["incident_id"] == incident["id"]


@pytest.mark.asyncio
async def test_clear_mitigation_not_found_returns_404(client, make_user, as_user):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    incident = await create_incident(client)

    response = await client.delete(mitigation_url(incident["id"]))

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_mitigation_actions_appear_in_incident_audit_log(client, make_user, as_user):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    incident = await create_incident(client)
    await client.post(mitigation_url(incident["id"]), json=mitigation_payload())
    await client.delete(mitigation_url(incident["id"]))

    response = await client.get(f"{INCIDENTS_URL}{incident['id']}/audit-log")

    assert response.status_code == 200
    actions = [entry["action"] for entry in response.json()]
    assert actions == ["INCIDENT_CREATED", "MITIGATION_CREATED", "MITIGATION_DELETED"]


@pytest.mark.asyncio
async def test_clear_mitigation_as_viewer_forbidden(client, make_user, as_user):
    responder = await make_user(role=UserRole.RESPONDER)
    as_user(responder)
    incident = await create_incident(client)
    await client.post(mitigation_url(incident["id"]), json=mitigation_payload())

    viewer = await make_user(role=UserRole.VIEWER)
    as_user(viewer)
    response = await client.delete(mitigation_url(incident["id"]))

    assert response.status_code == 403
