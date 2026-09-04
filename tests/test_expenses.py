"""Tests for V3-S3: Expense creation from validated values.

Covers:
- POST /extractions/{id}/expenses (success, validation failure, not found, isolation, idempotency).
- GET /expenses/{id} (detail with lines, not found, isolation).
- GET /expenses (list, empty, isolation).
- INV-1: total == base + vat.
- INV-3: document_id NOT NULL.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
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
    SourceDocument,
    Extraction,
    ExtractedValue,
    NormalizedValue,
    ValidatedValue,
    Expense,
    ExpenseLine,
    TaxLine,
)
from backend.main import create_app
from backend.utils import uuid7
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
        role="reader",
        state="active",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def test_session(db_session: DbSession, test_user: User, test_org: Organization) -> SessionModel:
    token = "test-worker-token"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    session = SessionModel(
        id=token_hash,
        user_id=test_user.id,
        organization_id=test_org.id,
        role="reader",
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
def auth_headers(client: TestClient, test_user: User, test_org: Organization) -> dict:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "testpass123"},
    )
    assert response.status_code == 200
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _create_full_pipeline(
    db: DbSession,
    org: Organization,
    user: User,
    values: list | None = None,
) -> tuple:
    """Create a document + extraction + normalized + validated values.

    Returns (document_id_str, extraction_id_str) to avoid DetachedInstanceError.
    Also creates a TaxRate and Supplier needed for expense creation.
    """
    if values is None:
        values = [
            {"field": "supplier_name", "raw": "Acme Corp SL", "norm": "Acme Corp SL", "val": "Acme Corp SL"},
            {"field": "total_amount", "raw": "121.00", "norm": "121.00", "val": "121.00"},
            {"field": "base_amount", "raw": "100.00", "norm": "100.00", "val": "100.00"},
            {"field": "vat_amount", "raw": "21.00", "norm": "21.00", "val": "21.00"},
            {"field": "currency", "raw": "EUR", "norm": "EUR", "val": "EUR"},
            {"field": "invoice_date", "raw": "2024-01-15", "norm": "2024-01-15", "val": "2024-01-15"},
            {"field": "vat_rate", "raw": "21%", "norm": "21", "val": "21"},
        ]

    # Create tax rate (needed for expense creation).
    from backend.models.catalog import TaxRate
    from datetime import date as date_type

    existing_tr = (
        db.execute(select(TaxRate).where(TaxRate.owner_id == org.id))
        .scalars()
        .first()
    )
    if existing_tr is None:
        tr = TaxRate(
            id=uuid7(),
            owner_id=org.id,
            code="VAT21",
            description="IVA 21%",
            tax_type="vat",
            percentage=Decimal("21.00"),
            valid_from=date_type(2020, 1, 1),
        )
        db.add(tr)
        db.flush()

    content = b"test document content"
    fingerprint = hashlib.sha256(content).hexdigest()
    safe_name = f"{uuid7()}.xml"

    doc = SourceDocument(
        id=uuid7(),
        owner_id=org.id,
        safe_name=safe_name,
        original_filename="test.xml",
        fingerprint_sha256=fingerprint,
        doc_type="received_invoice",
        format_detected="xml",
        size_bytes=len(content),
        uploaded_by=user.id,
        state="validated",
    )
    db.add(doc)
    db.flush()

    extraction = Extraction(
        id=uuid7(),
        owner_id=org.id,
        document_id=doc.id,
        method="xml_schema",
        state="completed",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )
    db.add(extraction)
    db.flush()

    for v in values:
        ev = ExtractedValue(
            id=uuid7(),
            owner_id=org.id,
            extraction_id=extraction.id,
            field=v["field"],
            raw_value=v["raw"],
            confidence=0.95,
            provenance={"method": "xml_schema", "rule": f"xml:{v['field']}"},
        )
        db.add(ev)
        db.flush()

        nv = NormalizedValue(
            id=uuid7(),
            owner_id=org.id,
            extracted_value_id=ev.id,
            field=v["field"],
            normalized_value=v["norm"],
            normalization_rule="test_rule",
        )
        db.add(nv)
        db.flush()

        vv = ValidatedValue(
            id=uuid7(),
            owner_id=org.id,
            normalized_value_id=nv.id,
            field=v["field"],
            validated_value=v["val"],
            validation_result="passed",
            rules_applied=json.dumps([{"rule_id": "VR-TEST", "severity": "BLOCK", "passed": True, "message": ""}]),
        )
        db.add(vv)

    db.commit()

    from backend.config import get_settings
    settings = get_settings()
    directory = os.path.join(settings.DOCUMENT_STORAGE_PATH, str(org.id))
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, fingerprint)
    with open(path, "wb") as fh:
        fh.write(content)

    return str(doc.id), str(extraction.id)


# --- POST /extractions/{id}/expenses tests ---


class TestCreateExpenseEndpoint:
    def test_create_expense_success(self, client, auth_headers, db_session, test_org, test_user):
        """Create an expense from validated values."""
        doc_id, extraction_id = _create_full_pipeline(
            db_session, test_org, test_user
        )

        response = client.post(
            f"/api/v1/extractions/{extraction_id}/expenses",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["document_id"] == doc_id
        assert body["total"] == 121.00
        assert body["state"] == "draft"

        # Verify expense exists in DB.
        expense = (
            db_session.execute(
                select(Expense).where(Expense.id == uuid.UUID(body["expense_id"]))
            )
            .scalars()
            .first()
        )
        assert expense is not None
        assert expense.total == Decimal("121.00")
        assert expense.base_total == Decimal("100.00")
        assert expense.vat_total == Decimal("21.00")
        assert expense.currency == "EUR"
        assert expense.state == "draft"

    def test_create_expense_inv1(self, client, auth_headers, db_session, test_org, test_user):
        """INV-1: total == base + vat."""
        doc_id, extraction_id = _create_full_pipeline(
            db_session, test_org, test_user
        )

        response = client.post(
            f"/api/v1/extractions/{extraction_id}/expenses",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()

        expense = (
            db_session.execute(
                select(Expense).where(Expense.id == uuid.UUID(body["expense_id"]))
            )
            .scalars()
            .first()
        )
        # INV-1: total == base + vat
        assert expense.total == expense.base_total + expense.vat_total

    def test_create_expense_with_failed_validation(self, client, auth_headers, db_session, test_org, test_user):
        """Cannot create expense if validation has BLOCK failures."""
        # Create pipeline with a failed validation.
        values = [
            {"field": "supplier_name", "raw": "Acme", "norm": "Acme", "val": "Acme"},
            {"field": "total_amount", "raw": "999.00", "norm": "999.00", "val": "999.00"},
            {"field": "base_amount", "raw": "100.00", "norm": "100.00", "val": "100.00"},
            {"field": "vat_amount", "raw": "21.00", "norm": "21.00", "val": "21.00"},
            {"field": "currency", "raw": "EUR", "norm": "EUR", "val": "EUR"},
            {"field": "invoice_date", "raw": "2024-01-15", "norm": "2024-01-15", "val": "2024-01-15"},
        ]
        doc_id, extraction_id = _create_full_pipeline(
            db_session, test_org, test_user, values=values
        )

        # Mark total_amount as failed.
        failed_vv = (
            db_session.execute(
                select(ValidatedValue).where(
                    ValidatedValue.field == "total_amount",
                    ValidatedValue.normalized_value_id.in_(
                        select(NormalizedValue.id).where(
                            NormalizedValue.extracted_value_id.in_(
                                select(ExtractedValue.id).where(
                                    ExtractedValue.extraction_id == uuid.UUID(extraction_id)
                                )
                            )
                        )
                    ),
                )
            )
            .scalars()
            .first()
        )
        failed_vv.validation_result = "failed"
        db_session.commit()

        response = client.post(
            f"/api/v1/extractions/{extraction_id}/expenses",
            headers=auth_headers,
        )
        assert response.status_code == 409

    def test_create_expense_not_found(self, client, auth_headers):
        """Create expense for non-existent extraction -> 404."""
        fake_id = uuid.uuid4()
        response = client.post(
            f"/api/v1/extractions/{fake_id}/expenses",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_create_expense_isolation(self, client, db_session, test_org, other_org, test_user):
        """Another org cannot create expense from this extraction -> 404."""
        doc_id, extraction_id = _create_full_pipeline(
            db_session, test_org, test_user
        )

        other_user = User(
            id=uuid.uuid4(),
            organization_id=other_org.id,
            username="otheruser",
            email="other@example.com",
            password_hash=_hash_password("otherpass123"),
            role="reader",
            state="active",
        )
        db_session.add(other_user)
        db_session.commit()
        db_session.refresh(other_user)

        response = client.post(
            "/api/v1/auth/login",
            json={"username": "otheruser", "password": "otherpass123"},
        )
        assert response.status_code == 200
        other_token = response.json()["token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}

        response = client.post(
            f"/api/v1/extractions/{extraction_id}/expenses",
            headers=other_headers,
        )
        assert response.status_code == 404

    def test_create_expense_idempotency(self, client, auth_headers, db_session, test_org, test_user):
        """Creating expense twice returns the same expense."""
        doc_id, extraction_id = _create_full_pipeline(
            db_session, test_org, test_user
        )

        response1 = client.post(
            f"/api/v1/extractions/{extraction_id}/expenses",
            headers=auth_headers,
        )
        assert response1.status_code == 200
        body1 = response1.json()

        response2 = client.post(
            f"/api/v1/extractions/{extraction_id}/expenses",
            headers=auth_headers,
        )
        assert response2.status_code == 200
        body2 = response2.json()
        assert body1["expense_id"] == body2["expense_id"]


# --- GET /expenses/{id} tests ---


class TestGetExpenseEndpoint:
    def test_get_expense(self, client, auth_headers, db_session, test_org, test_user):
        """Get an expense with its lines."""
        doc_id, extraction_id = _create_full_pipeline(
            db_session, test_org, test_user
        )

        create_resp = client.post(
            f"/api/v1/extractions/{extraction_id}/expenses",
            headers=auth_headers,
        )
        expense_id = create_resp.json()["expense_id"]

        response = client.get(
            f"/api/v1/expenses/{expense_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == expense_id
        assert body["total"] == 121.00
        assert body["state"] == "draft"
        assert len(body["lines"]) == 1
        assert len(body["tax_lines"]) == 1
        assert body["lines"][0]["amount"] == 100.00
        assert body["tax_lines"][0]["tax_type"] == "vat"
        assert body["tax_lines"][0]["tax_amount"] == 21.00

    def test_get_expense_not_found(self, client, auth_headers):
        """Get non-existent expense -> 404."""
        fake_id = uuid.uuid4()
        response = client.get(
            f"/api/v1/expenses/{fake_id}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_get_expense_isolation(self, client, auth_headers, db_session, test_org, other_org, test_user):
        """Another org cannot get this expense -> 404."""
        doc_id, extraction_id = _create_full_pipeline(
            db_session, test_org, test_user
        )

        create_resp = client.post(
            f"/api/v1/extractions/{extraction_id}/expenses",
            headers=auth_headers,
        )
        expense_id = create_resp.json()["expense_id"]

        other_user = User(
            id=uuid.uuid4(),
            organization_id=other_org.id,
            username="otheruser2",
            email="other2@example.com",
            password_hash=_hash_password("otherpass2"),
            role="reader",
            state="active",
        )
        db_session.add(other_user)
        db_session.commit()
        db_session.refresh(other_user)

        response = client.post(
            "/api/v1/auth/login",
            json={"username": "otheruser2", "password": "otherpass2"},
        )
        other_token = response.json()["token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}

        response = client.get(
            f"/api/v1/expenses/{expense_id}",
            headers=other_headers,
        )
        assert response.status_code == 404


# --- GET /expenses tests ---


class TestListExpensesEndpoint:
    def test_list_expenses(self, client, auth_headers, db_session, test_org, test_user):
        """List expenses for the organization."""
        doc_id, extraction_id = _create_full_pipeline(
            db_session, test_org, test_user
        )

        client.post(
            f"/api/v1/extractions/{extraction_id}/expenses",
            headers=auth_headers,
        )

        response = client.get(
            "/api/v1/expenses",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        assert len(body["expenses"]) == 1
        assert body["expenses"][0]["total"] == 121.00

    def test_list_expenses_empty(self, client, auth_headers):
        """List expenses with none -> empty."""
        response = client.get(
            "/api/v1/expenses",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 0
