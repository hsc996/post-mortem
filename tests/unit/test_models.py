from datetime import datetime, timedelta, timezone
import pytest
from src.models.account import Account
from src.models.incident import Incident, IncidentSeverity, IncidentStatus
from src.models.mitigation import MitigationState
from src.models.user import User, UserRole


@pytest.mark.asyncio
async def test_create_account(db_session):
    account = Account(name="Acme Corp")
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    assert account.id is not None
    assert account.name == "Acme Corp"
    assert account.created_at is not None


@pytest.mark.asyncio
async def test_create_user_and_full_name_property(db_session):
    account = Account(name="Acme Corp")
    db_session.add(account)
    await db_session.commit()

    user = User(
        account_id=account.id,
        email="dev@pulseguard.io",
        hashed_password="hashed_secret_123",
        first_name="Hannah",
        last_name="Scaife",
        role=UserRole.RESPONDER,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.id is not None
    assert user.full_name == "Hannah Scaife"
    assert user.role == UserRole.RESPONDER


@pytest.mark.asyncio
async def test_user_account_name_property(db_session):
    account = Account(name="Acme Corp")
    db_session.add(account)
    await db_session.commit()

    user = User(
        account_id=account.id,
        email="dev2@pulseguard.io",
        hashed_password="hashed_secret_123",
        first_name="Hannah",
        last_name="Scaife",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.account_name == "Acme Corp"


@pytest.mark.asyncio
async def test_mitigation_ttl_expiration_logic(db_session):
    account = Account(name="Acme Corp")
    db_session.add(account)
    await db_session.commit()

    user = User(
        account_id=account.id,
        email="admin@pulseguard.io",
        hashed_password="hash",
        first_name="Admin",
        last_name="User",
    )
    db_session.add(user)
    await db_session.commit()

    incident = Incident(
        account_id=account.id,
        title="API Gateway High Latency",
        description="P99 response time spiked to 2.5s",
        service_name="api-gateway",
        severity=IncidentSeverity.HIGH,
        reporter_id=user.id,
    )
    db_session.add(incident)
    await db_session.commit()

    # Applied 90 minutes ago with a 60-minute TTL -> should be expired
    past_time = datetime.now(timezone.utc) - timedelta(minutes=90)
    mitigation = MitigationState(
        account_id=account.id,
        incident_id=incident.id,
        summary="Rerouted 30% of traffic to backup cluster",
        ttl_minutes=60,
        applied_at=past_time,
        applied_by_id=user.id,
    )
    db_session.add(mitigation)
    await db_session.commit()

    assert mitigation.is_expired is True


@pytest.mark.asyncio
async def test_active_mitigation_ttl(db_session):
    account = Account(name="Acme Corp")
    db_session.add(account)
    await db_session.commit()

    user = User(
        account_id=account.id,
        email="responder@pulseguard.io",
        hashed_password="hash",
        first_name="Alex",
        last_name="Rivera",
    )
    db_session.add(user)
    await db_session.commit()

    incident = Incident(
        account_id=account.id,
        title="DB Lock Contention",
        description="High lock waits on incidents table",
        service_name="postgres",
        reporter_id=user.id,
    )
    db_session.add(incident)
    await db_session.commit()

    # Applied just now with a 60-minute TTL -> should NOT be expired
    mitigation = MitigationState(
        account_id=account.id,
        incident_id=incident.id,
        summary="Killed long-running analytical query",
        ttl_minutes=60,
        applied_at=datetime.now(timezone.utc),
        applied_by_id=user.id,
    )
    db_session.add(mitigation)
    await db_session.commit()

    assert mitigation.is_expired is False
