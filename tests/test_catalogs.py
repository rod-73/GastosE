"""Tests for V6-S2 (Catalog CRUD).

Covers:
- Categories: create, list, get, update, deactivate.
- Payment Methods: create, list, get, update, deactivate.
- Tax Rates: create, list, get, update, deactivate.
- Currencies: list, get.
- Isolation: another org cannot see/modify.
- Audit events created for create/update/deactivate.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
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
    Category,
    PaymentMethod,
    TaxRate,
    Currency,
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
    token = "test-catalog-token"
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
    token = "test-catalog-token"
    return {"Authorization": f"Bearer {token}"}


# --- Category Tests ---


def test_create_category(client, auth_header, db_session, test_org):
    """FR-CAT-1: Create a category."""
    resp = client.post(
        "/api/v1/categories",
        json={
            "name": "Office Supplies",
            "description": "Pens, paper, etc.",
        },
        headers=auth_header,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Office Supplies"
    assert data["state"] == "active"

    # Verify in DB.
    category = db_session.execute(
        select(Category).where(Category.owner_id == test_org.id)
    ).scalars().first()
    assert category is not None
    assert category.name == "Office Supplies"


def test_create_category_missing_name(client, auth_header):
    """Category name is required."""
    resp = client.post(
        "/api/v1/categories",
        json={"name": ""},
        headers=auth_header,
    )
    assert resp.status_code == 409


def test_list_categories(client, auth_header):
    """List categories."""
    client.post(
        "/api/v1/categories",
        json={"name": "Alpha"},
        headers=auth_header,
    )
    client.post(
        "/api/v1/categories",
        json={"name": "Beta"},
        headers=auth_header,
    )

    resp = client.get("/api/v1/categories", headers=auth_header)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    names = [c["name"] for c in data["categories"]]
    assert "Alpha" in names
    assert "Beta" in names


def test_get_category(client, auth_header):
    """Get a single category."""
    create_resp = client.post(
        "/api/v1/categories",
        json={"name": "Alpha"},
        headers=auth_header,
    )
    category_id = create_resp.json()["id"]

    resp = client.get(f"/api/v1/categories/{category_id}", headers=auth_header)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Alpha"


def test_get_category_not_found(client, auth_header):
    """404 for non-existent category."""
    resp = client.get(
        f"/api/v1/categories/{uuid.uuid4()}",
        headers=auth_header,
    )
    assert resp.status_code == 404


def test_update_category(client, auth_header):
    """Update a category."""
    create_resp = client.post(
        "/api/v1/categories",
        json={"name": "Alpha"},
        headers=auth_header,
    )
    category_id = create_resp.json()["id"]

    resp = client.put(
        f"/api/v1/categories/{category_id}",
        json={"name": "Alpha Renamed"},
        headers=auth_header,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Alpha Renamed"


def test_deactivate_category(client, auth_header):
    """Deactivate a category."""
    create_resp = client.post(
        "/api/v1/categories",
        json={"name": "Alpha"},
        headers=auth_header,
    )
    category_id = create_resp.json()["id"]

    resp = client.post(
        f"/api/v1/categories/{category_id}/deactivate",
        json={"reason": "No longer needed"},
        headers=auth_header,
    )
    assert resp.status_code == 200
    assert resp.json()["state"] == "inactive"


# --- Payment Method Tests ---


def test_create_payment_method(client, auth_header):
    """Create a payment method."""
    resp = client.post(
        "/api/v1/payment-methods",
        json={"name": "Credit Card"},
        headers=auth_header,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Credit Card"
    assert data["state"] == "active"


def test_list_payment_methods(client, auth_header):
    """List payment methods."""
    client.post(
        "/api/v1/payment-methods",
        json={"name": "Cash"},
        headers=auth_header,
    )
    client.post(
        "/api/v1/payment-methods",
        json={"name": "Bank Transfer"},
        headers=auth_header,
    )

    resp = client.get("/api/v1/payment-methods", headers=auth_header)
    assert resp.status_code == 200
    assert resp.json()["count"] == 2


def test_get_payment_method(client, auth_header):
    """Get a single payment method."""
    create_resp = client.post(
        "/api/v1/payment-methods",
        json={"name": "Cash"},
        headers=auth_header,
    )
    pm_id = create_resp.json()["id"]

    resp = client.get(f"/api/v1/payment-methods/{pm_id}", headers=auth_header)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Cash"


def test_update_payment_method(client, auth_header):
    """Update a payment method."""
    create_resp = client.post(
        "/api/v1/payment-methods",
        json={"name": "Cash"},
        headers=auth_header,
    )
    pm_id = create_resp.json()["id"]

    resp = client.put(
        f"/api/v1/payment-methods/{pm_id}",
        json={"name": "Cash (Updated)"},
        headers=auth_header,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Cash (Updated)"


def test_deactivate_payment_method(client, auth_header):
    """Deactivate a payment method."""
    create_resp = client.post(
        "/api/v1/payment-methods",
        json={"name": "Cash"},
        headers=auth_header,
    )
    pm_id = create_resp.json()["id"]

    resp = client.post(
        f"/api/v1/payment-methods/{pm_id}/deactivate",
        json={"reason": "Deprecated"},
        headers=auth_header,
    )
    assert resp.status_code == 200
    assert resp.json()["state"] == "inactive"


# --- Tax Rate Tests ---


def test_create_tax_rate(client, auth_header):
    """Create a tax rate."""
    resp = client.post(
        "/api/v1/tax-rates",
        json={
            "code": "IVA21",
            "tax_type": "vat",
            "percentage": 21.0,
            "valid_from": "2024-01-01",
            "description": "Standard VAT",
        },
        headers=auth_header,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["code"] == "IVA21"
    assert data["tax_type"] == "vat"
    assert float(data["percentage"]) == 21.0


def test_create_tax_rate_invalid_type(client, auth_header):
    """Reject invalid tax type."""
    resp = client.post(
        "/api/v1/tax-rates",
        json={
            "code": "INVALID",
            "tax_type": "invalid",
            "percentage": 10.0,
            "valid_from": "2024-01-01",
        },
        headers=auth_header,
    )
    assert resp.status_code == 409


def test_create_tax_rate_invalid_percentage(client, auth_header):
    """Reject percentage > 100."""
    resp = client.post(
        "/api/v1/tax-rates",
        json={
            "code": "TOO_HIGH",
            "tax_type": "vat",
            "percentage": 150.0,
            "valid_from": "2024-01-01",
        },
        headers=auth_header,
    )
    assert resp.status_code == 409


def test_list_tax_rates(client, auth_header):
    """List tax rates."""
    client.post(
        "/api/v1/tax-rates",
        json={
            "code": "IVA21",
            "tax_type": "vat",
            "percentage": 21.0,
            "valid_from": "2024-01-01",
        },
        headers=auth_header,
    )
    client.post(
        "/api/v1/tax-rates",
        json={
            "code": "RET15",
            "tax_type": "withholding",
            "percentage": 15.0,
            "valid_from": "2024-01-01",
        },
        headers=auth_header,
    )

    resp = client.get("/api/v1/tax-rates", headers=auth_header)
    assert resp.status_code == 200
    assert resp.json()["count"] == 2


def test_list_tax_rates_filter_by_type(client, auth_header):
    """Filter tax rates by type."""
    client.post(
        "/api/v1/tax-rates",
        json={
            "code": "IVA21",
            "tax_type": "vat",
            "percentage": 21.0,
            "valid_from": "2024-01-01",
        },
        headers=auth_header,
    )
    client.post(
        "/api/v1/tax-rates",
        json={
            "code": "RET15",
            "tax_type": "withholding",
            "percentage": 15.0,
            "valid_from": "2024-01-01",
        },
        headers=auth_header,
    )

    resp = client.get(
        "/api/v1/tax-rates?tax_type=vat",
        headers=auth_header,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["tax_rates"][0]["code"] == "IVA21"


def test_get_tax_rate(client, auth_header):
    """Get a single tax rate."""
    create_resp = client.post(
        "/api/v1/tax-rates",
        json={
            "code": "IVA21",
            "tax_type": "vat",
            "percentage": 21.0,
            "valid_from": "2024-01-01",
        },
        headers=auth_header,
    )
    tax_rate_id = create_resp.json()["id"]

    resp = client.get(f"/api/v1/tax-rates/{tax_rate_id}", headers=auth_header)
    assert resp.status_code == 200
    assert resp.json()["code"] == "IVA21"


def test_update_tax_rate(client, auth_header):
    """Update a tax rate."""
    create_resp = client.post(
        "/api/v1/tax-rates",
        json={
            "code": "IVA21",
            "tax_type": "vat",
            "percentage": 21.0,
            "valid_from": "2024-01-01",
        },
        headers=auth_header,
    )
    tax_rate_id = create_resp.json()["id"]

    resp = client.put(
        f"/api/v1/tax-rates/{tax_rate_id}",
        json={"percentage": 22.0},
        headers=auth_header,
    )
    assert resp.status_code == 200
    assert float(resp.json()["percentage"]) == 22.0


def test_deactivate_tax_rate(client, auth_header):
    """Deactivate a tax rate (set valid_until to today)."""
    create_resp = client.post(
        "/api/v1/tax-rates",
        json={
            "code": "IVA21",
            "tax_type": "vat",
            "percentage": 21.0,
            "valid_from": "2024-01-01",
        },
        headers=auth_header,
    )
    tax_rate_id = create_resp.json()["id"]

    resp = client.post(
        f"/api/v1/tax-rates/{tax_rate_id}/deactivate",
        json={"reason": "Rate changed"},
        headers=auth_header,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid_until"] is not None
    assert data["valid_until"] == date.today().isoformat()


# --- Currency Tests ---


def test_list_currencies(client, auth_header, db_session):
    """List currencies (global catalog)."""
    # Seed some currencies.
    for code, name, decimals in [("EUR", "Euro", 2), ("USD", "US Dollar", 2), ("GBP", "British Pound", 2)]:
        db_session.add(Currency(code=code, name=name, decimals=decimals))
    db_session.commit()

    resp = client.get("/api/v1/currencies", headers=auth_header)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 3
    codes = [c["code"] for c in data["currencies"]]
    assert "EUR" in codes
    assert "USD" in codes


def test_get_currency(client, auth_header, db_session):
    """Get a single currency."""
    db_session.add(Currency(code="EUR", name="Euro", decimals=2))
    db_session.commit()

    resp = client.get("/api/v1/currencies/EUR", headers=auth_header)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == "EUR"
    assert data["name"] == "Euro"
    assert data["decimals"] == 2


def test_get_currency_not_found(client, auth_header):
    """404 for non-existent currency."""
    resp = client.get("/api/v1/currencies/XYZ", headers=auth_header)
    assert resp.status_code == 404


# --- Isolation Tests ---


def test_category_isolation(client, auth_header, db_session, other_org):
    """Another org cannot see categories."""
    create_resp = client.post(
        "/api/v1/categories",
        json={"name": "Alpha"},
        headers=auth_header,
    )
    category_id = create_resp.json()["id"]

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

    other_token = "other-catalog-token"
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

    # Other org cannot see the category.
    resp = client.get(
        f"/api/v1/categories/{category_id}",
        headers=other_headers,
    )
    assert resp.status_code == 404

    # Other org cannot list it.
    resp = client.get("/api/v1/categories", headers=other_headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


# --- Audit Tests ---


def test_category_audit_events(client, auth_header, db_session, test_org):
    """Audit events created for category operations."""
    create_resp = client.post(
        "/api/v1/categories",
        json={"name": "Alpha"},
        headers=auth_header,
    )
    category_id = create_resp.json()["id"]

    client.put(
        f"/api/v1/categories/{category_id}",
        json={"name": "Alpha Renamed"},
        headers=auth_header,
    )

    client.post(
        f"/api/v1/categories/{category_id}/deactivate",
        json={"reason": "Test"},
        headers=auth_header,
    )

    events = db_session.execute(
        select(AuditEvent).where(
            AuditEvent.owner_id == test_org.id,
            AuditEvent.entity_type == "category",
            AuditEvent.entity_id == uuid.UUID(category_id),
        )
    ).scalars().all()

    actions = [e.action for e in events]
    assert "category.created" in actions
    assert "category.updated" in actions
    assert "category.deactivated" in actions
