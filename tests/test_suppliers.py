"""Tests for V6-S1 (Supplier CRUD).

Covers:
- POST /suppliers: create with valid NIF/CIF.
- POST /suppliers: reject invalid NIF/CIF.
- GET /suppliers: list with search and state filter.
- GET /suppliers/{id}: get single supplier.
- PUT /suppliers/{id}: update supplier.
- POST /suppliers/{id}/deactivate: deactivate supplier.
- Isolation: another org cannot see/modify.
- Audit events created for create/update/deactivate.
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
    Supplier,
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
    token = "test-supplier-token"
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
    token = "test-supplier-token"
    return {"Authorization": f"Bearer {token}"}


# --- Tests ---


def test_create_supplier_valid_nif(client, auth_header, db_session, test_org):
    """FR-SUP-1: Create supplier with valid NIF."""
    resp = client.post(
        "/api/v1/suppliers",
        json={
            "legal_name": "Empresa Ejemplo SL",
            "nif_cif": "12345678Z",
            "tax_address": "Calle Ejemplo 1, Madrid",
        },
        headers=auth_header,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["legal_name"] == "Empresa Ejemplo SL"
    assert data["nif_cif"] == "12345678Z"
    assert data["state"] == "active"
    assert data["tax_address"] == "Calle Ejemplo 1, Madrid"

    # Verify in DB.
    supplier = db_session.execute(
        select(Supplier).where(Supplier.owner_id == test_org.id)
    ).scalars().first()
    assert supplier is not None
    assert supplier.legal_name == "Empresa Ejemplo SL"


def test_create_supplier_valid_cif(client, auth_header, db_session, test_org):
    """FR-SUP-1: Create supplier with valid CIF."""
    resp = client.post(
        "/api/v1/suppliers",
        json={
            "legal_name": "Otra Empresa SA",
            "nif_cif": "A58812974",
        },
        headers=auth_header,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["nif_cif"] == "A58812974"
    assert data["state"] == "active"


def test_create_supplier_invalid_nif(client, auth_header):
    """FR-SUP-2: Reject invalid NIF/CIF check digit."""
    resp = client.post(
        "/api/v1/suppliers",
        json={
            "legal_name": "Empresa Invalida SL",
            "nif_cif": "12345678A",  # Wrong check letter.
        },
        headers=auth_header,
    )
    assert resp.status_code == 409
    assert "Invalid NIF/CIF" in resp.json()["detail"]


def test_create_supplier_missing_name(client, auth_header):
    """FR-SUP-1: Legal name is required."""
    resp = client.post(
        "/api/v1/suppliers",
        json={
            "legal_name": "",
            "nif_cif": "12345678Z",
        },
        headers=auth_header,
    )
    assert resp.status_code == 409


def test_create_supplier_missing_nif(client, auth_header):
    """FR-SUP-2: NIF/CIF is required."""
    resp = client.post(
        "/api/v1/suppliers",
        json={
            "legal_name": "Empresa SL",
            "nif_cif": "",
        },
        headers=auth_header,
    )
    assert resp.status_code == 409


def test_list_suppliers(client, auth_header, db_session, test_org):
    """FR-SUP-3: List suppliers."""
    # Create two suppliers.
    for name, nif in [("Alpha SL", "12345678Z"), ("Beta SL", "A58812974")]:
        client.post(
            "/api/v1/suppliers",
            json={"legal_name": name, "nif_cif": nif},
            headers=auth_header,
        )

    resp = client.get("/api/v1/suppliers", headers=auth_header)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    names = [s["legal_name"] for s in data["suppliers"]]
    assert "Alpha SL" in names
    assert "Beta SL" in names


def test_list_suppliers_search_by_name(client, auth_header):
    """FR-SUP-3: Search by name."""
    client.post(
        "/api/v1/suppliers",
        json={"legal_name": "Alpha SL", "nif_cif": "12345678Z"},
        headers=auth_header,
    )
    client.post(
        "/api/v1/suppliers",
        json={"legal_name": "Beta SL", "nif_cif": "A58812974"},
        headers=auth_header,
    )

    resp = client.get(
        "/api/v1/suppliers?search=alpha",
        headers=auth_header,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["suppliers"][0]["legal_name"] == "Alpha SL"


def test_list_suppliers_search_by_nif(client, auth_header):
    """FR-SUP-3: Search by NIF/CIF."""
    client.post(
        "/api/v1/suppliers",
        json={"legal_name": "Alpha SL", "nif_cif": "12345678Z"},
        headers=auth_header,
    )
    client.post(
        "/api/v1/suppliers",
        json={"legal_name": "Beta SL", "nif_cif": "A58812974"},
        headers=auth_header,
    )

    resp = client.get(
        "/api/v1/suppliers?search=12345678Z",
        headers=auth_header,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["suppliers"][0]["nif_cif"] == "12345678Z"


def test_list_suppliers_filter_by_state(client, auth_header):
    """FR-SUP-3: Filter by state."""
    client.post(
        "/api/v1/suppliers",
        json={"legal_name": "Alpha SL", "nif_cif": "12345678Z"},
        headers=auth_header,
    )
    # Deactivate it.
    resp = client.get("/api/v1/suppliers", headers=auth_header)
    supplier_id = resp.json()["suppliers"][0]["id"]
    client.post(
        f"/api/v1/suppliers/{supplier_id}/deactivate",
        json={"reason": "Test deactivation"},
        headers=auth_header,
    )

    resp = client.get(
        "/api/v1/suppliers?state=inactive",
        headers=auth_header,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["suppliers"][0]["state"] == "inactive"


def test_get_supplier(client, auth_header):
    """Get a single supplier."""
    create_resp = client.post(
        "/api/v1/suppliers",
        json={"legal_name": "Alpha SL", "nif_cif": "12345678Z"},
        headers=auth_header,
    )
    supplier_id = create_resp.json()["id"]

    resp = client.get(f"/api/v1/suppliers/{supplier_id}", headers=auth_header)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == supplier_id
    assert data["legal_name"] == "Alpha SL"


def test_get_supplier_not_found(client, auth_header):
    """404 for non-existent supplier."""
    resp = client.get(
        f"/api/v1/suppliers/{uuid.uuid4()}",
        headers=auth_header,
    )
    assert resp.status_code == 404


def test_update_supplier(client, auth_header):
    """Update supplier legal name."""
    create_resp = client.post(
        "/api/v1/suppliers",
        json={"legal_name": "Alpha SL", "nif_cif": "12345678Z"},
        headers=auth_header,
    )
    supplier_id = create_resp.json()["id"]

    resp = client.put(
        f"/api/v1/suppliers/{supplier_id}",
        json={"legal_name": "Alpha Renamed SL"},
        headers=auth_header,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["legal_name"] == "Alpha Renamed SL"


def test_update_supplier_invalid_nif(client, auth_header):
    """FR-SUP-2: Reject invalid NIF/CIF on update."""
    create_resp = client.post(
        "/api/v1/suppliers",
        json={"legal_name": "Alpha SL", "nif_cif": "12345678Z"},
        headers=auth_header,
    )
    supplier_id = create_resp.json()["id"]

    resp = client.put(
        f"/api/v1/suppliers/{supplier_id}",
        json={"nif_cif": "12345678A"},  # Wrong check letter.
        headers=auth_header,
    )
    assert resp.status_code == 409
    assert "Invalid NIF/CIF" in resp.json()["detail"]


def test_deactivate_supplier(client, auth_header):
    """FR-SUP-4: Deactivate supplier."""
    create_resp = client.post(
        "/api/v1/suppliers",
        json={"legal_name": "Alpha SL", "nif_cif": "12345678Z"},
        headers=auth_header,
    )
    supplier_id = create_resp.json()["id"]

    resp = client.post(
        f"/api/v1/suppliers/{supplier_id}/deactivate",
        json={"reason": "No longer doing business"},
        headers=auth_header,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "inactive"


def test_deactivate_already_inactive(client, auth_header):
    """Cannot deactivate an already inactive supplier."""
    create_resp = client.post(
        "/api/v1/suppliers",
        json={"legal_name": "Alpha SL", "nif_cif": "12345678Z"},
        headers=auth_header,
    )
    supplier_id = create_resp.json()["id"]

    # First deactivation.
    client.post(
        f"/api/v1/suppliers/{supplier_id}/deactivate",
        json={"reason": "First"},
        headers=auth_header,
    )

    # Second deactivation should fail.
    resp = client.post(
        f"/api/v1/suppliers/{supplier_id}/deactivate",
        json={"reason": "Second"},
        headers=auth_header,
    )
    assert resp.status_code == 409


def test_supplier_isolation(client, auth_header, db_session, other_org):
    """Another org cannot see or modify suppliers."""
    # Create a supplier in test_org.
    create_resp = client.post(
        "/api/v1/suppliers",
        json={"legal_name": "Alpha SL", "nif_cif": "12345678Z"},
        headers=auth_header,
    )
    supplier_id = create_resp.json()["id"]

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

    other_token = "other-supplier-token"
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

    # Other org cannot see the supplier.
    resp = client.get(
        f"/api/v1/suppliers/{supplier_id}",
        headers=other_headers,
    )
    assert resp.status_code == 404

    # Other org cannot list it.
    resp = client.get("/api/v1/suppliers", headers=other_headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


def test_supplier_audit_events(client, auth_header, db_session, test_org):
    """Audit events created for create, update, deactivate."""
    create_resp = client.post(
        "/api/v1/suppliers",
        json={"legal_name": "Alpha SL", "nif_cif": "12345678Z"},
        headers=auth_header,
    )
    supplier_id = create_resp.json()["id"]

    # Update.
    client.put(
        f"/api/v1/suppliers/{supplier_id}",
        json={"legal_name": "Alpha Renamed SL"},
        headers=auth_header,
    )

    # Deactivate.
    client.post(
        f"/api/v1/suppliers/{supplier_id}/deactivate",
        json={"reason": "Test"},
        headers=auth_header,
    )

    # Check audit events.
    events = db_session.execute(
        select(AuditEvent).where(
            AuditEvent.owner_id == test_org.id,
            AuditEvent.entity_type == "supplier",
            AuditEvent.entity_id == uuid.UUID(supplier_id),
        )
    ).scalars().all()

    actions = [e.action for e in events]
    assert "supplier.created" in actions
    assert "supplier.updated" in actions
    assert "supplier.deactivated" in actions
