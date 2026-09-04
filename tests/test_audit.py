"""Tests for V7-S1 (Audit log).

Covers:
- GET /audit-events: list with filters (entity_type, entity_id, action).
- GET /audit-events/{id}: get single event.
- Isolation: another org cannot see events.
- Append-only: no update/delete endpoints exist.
- Pagination: limit and offset.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.models import (
    Organization,
    User,
    Session as SessionModel,
    AuditEvent,
)
from backend.main import create_app
import bcrypt


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_path, monkeypatch):
    storage = tmp_path / "documents"
    storage.mkdir()
    monkeypatch.setenv("GASTOSE_DOCUMENT_STORAGE_PATH", str(storage))
    yield


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine) -> Generator[DbSession, None, None]:
    TestingSessionLocal = sessionmaker(bind=db_engine, autoflush=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def test_org(db_session: DbSession) -> Organization:
    org = Organization(id=uuid.uuid4(), name="Test Org", state="active")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture()
def other_org(db_session: DbSession) -> Organization:
    org = Organization(id=uuid.uuid4(), name="Other Org", state="active")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture()
def test_user(db_session: DbSession, test_org: Organization) -> User:
    user = User(
        id=uuid.uuid4(),
        organization_id=test_org.id,
        username="testuser",
        email="test@example.com",
        password_hash=_hash_password("testpass123"),
        role="approver",
        state="active",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def test_session(db_session: DbSession, test_user: User, test_org: Organization) -> SessionModel:
    token = "test-audit-token"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    session = SessionModel(
        id=token_hash,
        user_id=test_user.id,
        organization_id=test_org.id,
        role="approver",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        revoked_at=None,
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session


@pytest.fixture()
def client(
    db_engine,
    test_org: Organization,
    test_user: User,
    test_session: SessionModel,
) -> Generator[TestClient, None, None]:
    TestingSessionLocal = sessionmaker(bind=db_engine, autoflush=False)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.state.session_factory = TestingSessionLocal

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_header(test_session: SessionModel) -> dict:
    token = "test-audit-token"
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def seed_audit_events(db_session: DbSession, test_org: Organization, test_user: User) -> list:
    """Seed some audit events for testing."""
    events = []
    for i, (entity_type, action) in enumerate([
        ("supplier", "supplier.created"),
        ("supplier", "supplier.updated"),
        ("category", "category.created"),
        ("expense", "expense.accepted"),
        ("document", "document.uploaded"),
    ]):
        entity_id = uuid.uuid4()
        event = AuditEvent(
            id=uuid.uuid4(),
            owner_id=test_org.id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor=test_user.id,
            before_data=None if i == 0 else {"field": "old"},
            after_data={"field": "new"},
        )
        db_session.add(event)
        events.append(event)
    db_session.commit()
    return events


# --- Tests ---


def test_list_audit_events(client, auth_header, seed_audit_events):
    """List all audit events."""
    resp = client.get("/api/v1/audit-events", headers=auth_header)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 5
    assert len(data["events"]) == 5


def test_list_audit_events_filter_by_entity_type(client, auth_header, seed_audit_events):
    """Filter by entity_type."""
    resp = client.get(
        "/api/v1/audit-events?entity_type=supplier",
        headers=auth_header,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    for event in data["events"]:
        assert event["entity_type"] == "supplier"


def test_list_audit_events_filter_by_action(client, auth_header, seed_audit_events):
    """Filter by action."""
    resp = client.get(
        "/api/v1/audit-events?action=supplier.created",
        headers=auth_header,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["events"][0]["action"] == "supplier.created"


def test_list_audit_events_filter_by_entity_id(client, auth_header, seed_audit_events):
    """Filter by entity_id."""
    entity_id = seed_audit_events[0].entity_id
    resp = client.get(
        f"/api/v1/audit-events?entity_id={entity_id}",
        headers=auth_header,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["events"][0]["entity_id"] == str(entity_id)


def test_list_audit_events_pagination(client, auth_header, seed_audit_events):
    """Pagination with limit and offset."""
    resp = client.get(
        "/api/v1/audit-events?limit=2&offset=0",
        headers=auth_header,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert len(data["events"]) == 2

    resp = client.get(
        "/api/v1/audit-events?limit=2&offset=2",
        headers=auth_header,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert len(data["events"]) == 2


def test_get_audit_event(client, auth_header, seed_audit_events):
    """Get a single audit event."""
    event_id = seed_audit_events[0].id
    resp = client.get(
        f"/api/v1/audit-events/{event_id}",
        headers=auth_header,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(event_id)
    assert data["entity_type"] == "supplier"
    assert data["action"] == "supplier.created"
    assert data["after_data"] == {"field": "new"}


def test_get_audit_event_not_found(client, auth_header):
    """404 for non-existent audit event."""
    resp = client.get(
        f"/api/v1/audit-events/{uuid.uuid4()}",
        headers=auth_header,
    )
    assert resp.status_code == 404


def test_audit_event_isolation(client, auth_header, db_session, other_org, test_user, test_org):
    """Another org cannot see audit events."""
    # Seed an event in test_org.
    event = AuditEvent(
        id=uuid.uuid4(),
        owner_id=test_org.id,
        entity_type="supplier",
        entity_id=uuid.uuid4(),
        action="supplier.created",
        actor=test_user.id,
        after_data={"name": "Test"},
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    # Create a session for other_org.
    other_user = User(
        id=uuid.uuid4(),
        organization_id=other_org.id,
        username="otheruser",
        email="other@example.com",
        password_hash=_hash_password("otherpass123"),
        role="approver",
        state="active",
    )
    db_session.add(other_user)
    db_session.commit()
    db_session.refresh(other_user)

    other_token = "other-audit-token"
    other_token_hash = hashlib.sha256(other_token.encode()).hexdigest()
    other_session = SessionModel(
        id=other_token_hash,
        user_id=other_user.id,
        organization_id=other_org.id,
        role="approver",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        revoked_at=None,
    )
    db_session.add(other_session)
    db_session.commit()

    other_headers = {"Authorization": f"Bearer {other_token}"}

    # Other org cannot see the event.
    resp = client.get(
        f"/api/v1/audit-events/{event.id}",
        headers=other_headers,
    )
    assert resp.status_code == 404

    # Other org cannot list it.
    resp = client.get("/api/v1/audit-events", headers=other_headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


def test_audit_events_have_before_after_data(client, auth_header, seed_audit_events):
    """Audit events preserve before/after data (INV-10)."""
    resp = client.get("/api/v1/audit-events", headers=auth_header)
    assert resp.status_code == 200
    data = resp.json()

    # First event has no before_data (creation).
    events_by_action = {e["action"]: e for e in data["events"]}
    created = events_by_action["supplier.created"]
    assert created["before_data"] is None
    assert created["after_data"] is not None

    # Updated event has both before and after.
    updated = events_by_action["supplier.updated"]
    assert updated["before_data"] is not None
    assert updated["after_data"] is not None


def test_no_update_delete_endpoints(client, auth_header):
    """NFR-1: No UPDATE or DELETE endpoints for audit events."""
    # PUT should return 405 Method Not Allowed.
    event_id = uuid.uuid4()
    resp = client.put(
        f"/api/v1/audit-events/{event_id}",
        json={"action": "hacked"},
        headers=auth_header,
    )
    assert resp.status_code == 405

    # DELETE should return 405 Method Not Allowed.
    resp = client.delete(
        f"/api/v1/audit-events/{event_id}",
        headers=auth_header,
    )
    assert resp.status_code == 405
