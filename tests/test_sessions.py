"""Tests for V8-S1 (Session management).

Covers:
- POST /auth/login: create session, return token.
- POST /auth/logout: revoke current session.
- GET /sessions: list active sessions.
- POST /sessions/{id}/revoke: revoke specific session.
- POST /sessions/revoke-all: revoke all sessions.
- Session expiry: expired sessions are rejected.
- Revoked sessions are rejected.
- Isolation: user cannot revoke another user's session.
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
    token = "test-session-token"
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
    token = "test-session-token"
    return {"Authorization": f"Bearer {token}"}


# --- Login/Logout Tests ---


def test_login_success(client, db_session, test_org, test_user):
    """Login with valid credentials returns a token."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "testpass123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    assert "expires_at" in data
    assert len(data["token"]) > 0


def test_login_invalid_password(client):
    """Login with wrong password returns 401."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "wrongpass"},
    )
    assert resp.status_code == 401


def test_login_inactive_user(client, db_session, test_org):
    """Login with inactive user returns 401."""
    inactive_user = User(
        id=uuid.uuid4(),
        organization_id=test_org.id,
        username="inactiveuser",
        email="inactive@example.com",
        password_hash=_hash_password("inactpass123"),
        role="reader",
        state="inactive",
    )
    db_session.add(inactive_user)
    db_session.commit()

    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "inactiveuser", "password": "inactpass123"},
    )
    assert resp.status_code == 401


def test_logout_revokes_session(client, auth_header, db_session, test_session):
    """Logout revokes the current session."""
    resp = client.post("/api/v1/auth/logout", headers=auth_header)
    assert resp.status_code == 204

    # Verify session is revoked in DB.
    db_session.refresh(test_session)
    assert test_session.revoked_at is not None


def test_logout_idempotent(client, db_session, test_user, test_org, test_session):
    """Logout is idempotent (204 on repeat)."""
    # First logout.
    client.post("/api/v1/auth/logout", headers={"Authorization": "Bearer test-session-token"})

    # Create a new session for the second logout.
    new_token = "second-logout-token"
    new_hash = hashlib.sha256(new_token.encode()).hexdigest()
    new_session = SessionModel(
        id=new_hash,
        user_id=test_user.id,
        organization_id=test_org.id,
        role="approver",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        revoked_at=None,
    )
    db_session.add(new_session)
    db_session.commit()

    # Second logout with the new token.
    resp = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {new_token}"})
    assert resp.status_code == 204


def test_revoked_session_rejected(client, db_session, test_session):
    """Revoked sessions are rejected (401)."""
    # Revoke the session.
    test_session.revoked_at = datetime.now(timezone.utc)
    db_session.commit()

    token = "test-session-token"
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/v1/suppliers", headers=headers)
    assert resp.status_code == 401


def test_expired_session_rejected(client, db_session, test_session):
    """Expired sessions are rejected (401)."""
    # Expire the session.
    test_session.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()

    token = "test-session-token"
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/v1/suppliers", headers=headers)
    assert resp.status_code == 401


# --- Session List Tests ---


def test_list_sessions(client, auth_header, db_session, test_user, test_org):
    """List active sessions for the current user."""
    # Create an additional session.
    extra_token = "extra-session-token"
    extra_hash = hashlib.sha256(extra_token.encode()).hexdigest()
    extra_session = SessionModel(
        id=extra_hash,
        user_id=test_user.id,
        organization_id=test_org.id,
        role="approver",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        revoked_at=None,
    )
    db_session.add(extra_session)
    db_session.commit()

    resp = client.get("/api/v1/sessions", headers=auth_header)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    # One should be marked as current.
    current_sessions = [s for s in data["sessions"] if s["is_current"]]
    assert len(current_sessions) == 1


def test_list_sessions_excludes_revoked(client, auth_header, db_session, test_user, test_org, test_session):
    """Revoked sessions are not listed."""
    # Revoke the current session.
    test_session.revoked_at = datetime.now(timezone.utc)
    db_session.commit()

    # Create a new session.
    new_token = "new-session-token"
    new_hash = hashlib.sha256(new_token.encode()).hexdigest()
    new_session = SessionModel(
        id=new_hash,
        user_id=test_user.id,
        organization_id=test_org.id,
        role="approver",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        revoked_at=None,
    )
    db_session.add(new_session)
    db_session.commit()

    # Use the new session to list.
    headers = {"Authorization": f"Bearer {new_token}"}
    resp = client.get("/api/v1/sessions", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    # Only the new session should be listed (the old one is revoked).
    assert data["count"] == 1


# --- Session Revocation Tests ---


def test_revoke_session(client, auth_header, db_session, test_user, test_org):
    """Revoke a specific session."""
    # Create an additional session.
    extra_token = "extra-revoke-token"
    extra_hash = hashlib.sha256(extra_token.encode()).hexdigest()
    extra_session = SessionModel(
        id=extra_hash,
        user_id=test_user.id,
        organization_id=test_org.id,
        role="approver",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        revoked_at=None,
    )
    db_session.add(extra_session)
    db_session.commit()

    # Revoke it.
    resp = client.post(
        f"/api/v1/sessions/{extra_hash}/revoke",
        headers=auth_header,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["revoked"] is True

    # Verify in DB.
    db_session.refresh(extra_session)
    assert extra_session.revoked_at is not None


def test_revoke_session_not_found(client, auth_header):
    """404 for non-existent session."""
    resp = client.post(
        "/api/v1/sessions/nonexistent/revoke",
        headers=auth_header,
    )
    assert resp.status_code == 404


def test_revoke_session_permission_denied(client, db_session, test_user, test_org, other_org, test_session):
    """User cannot revoke another user's session."""
    # Create a user in other_org.
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

    # Create a session for the other user.
    other_token = "other-revoke-token"
    other_hash = hashlib.sha256(other_token.encode()).hexdigest()
    other_session = SessionModel(
        id=other_hash,
        user_id=other_user.id,
        organization_id=other_org.id,
        role="approver",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        revoked_at=None,
    )
    db_session.add(other_session)
    db_session.commit()

    # Try to revoke with test_user's token (non-admin).
    headers = {"Authorization": "Bearer test-session-token"}
    resp = client.post(
        f"/api/v1/sessions/{other_hash}/revoke",
        headers=headers,
    )
    assert resp.status_code == 404  # Permission denied => 404 (not found for this user).


def test_revoke_all_sessions(client, auth_header, db_session, test_user, test_org):
    """Revoke all sessions for the current user."""
    # Create additional sessions.
    for i in range(3):
        token = f"revoke-all-token-{i}"
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

    # Revoke all.
    resp = client.post(
        "/api/v1/sessions/revoke-all",
        headers=auth_header,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["revoked"] is True
    assert "4" in data["message"]  # Current + 3 additional.

    # Verify all are revoked.
    sessions = db_session.execute(
        select(SessionModel).where(SessionModel.user_id == test_user.id)
    ).scalars().all()
    for s in sessions:
        assert s.revoked_at is not None
