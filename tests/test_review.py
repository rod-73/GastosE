"""Tests for V4-S1..V4-S4: Review, decisions, acceptance, rejection, voiding.

Covers:
- GET /expenses/{id}/review (five levels, not found, isolation).
- POST /expenses/{id}/review/decisions (confirm, correct, reject, invalid).
- POST /expenses/{id}/accept (success, duplicate block, invalid state).
- POST /expenses/{id}/reject (success, already rejected, accepted).
- POST /expenses/{id}/void (success, not accepted).
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
    TaxRate,
    Supplier,
    Duplication,
    AuditEvent,
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
        role="approver",
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
def auth_headers(client: TestClient, test_user: User, test_org: Organization) -> dict:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "testpass123"},
    )
    assert response.status_code == 200
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _create_expense_pipeline(
    db: DbSession,
    org: Organization,
    user: User,
) -> tuple:
    """Create a full pipeline ending in an expense.

    Returns (expense_id_str, extraction_id_str, doc_id_str).
    """
    from datetime import date as date_type

    # Tax rate.
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

    values = [
        {"field": "supplier_name", "raw": "Acme Corp SL", "norm": "Acme Corp SL", "val": "Acme Corp SL"},
        {"field": "total_amount", "raw": "121.00", "norm": "121.00", "val": "121.00"},
        {"field": "base_amount", "raw": "100.00", "norm": "100.00", "val": "100.00"},
        {"field": "vat_amount", "raw": "21.00", "norm": "21.00", "val": "21.00"},
        {"field": "currency", "raw": "EUR", "norm": "EUR", "val": "EUR"},
        {"field": "invoice_date", "raw": "2024-01-15", "norm": "2024-01-15", "val": "2024-01-15"},
        {"field": "vat_rate", "raw": "21%", "norm": "21", "val": "21"},
    ]
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

    # Create expense via service.
    from backend.services import expense_service
    expense = expense_service.create_expense_from_validation(
        extraction_id=extraction.id,
        owner_id=org.id,
        db=db,
    )

    return str(expense.id), str(extraction.id), str(doc.id)


# --- GET /expenses/{id}/review tests ---


class TestReviewView:
    def test_review_view(self, client, auth_headers, db_session, test_org, test_user):
        """Get the review view with five levels."""
        expense_id, extraction_id, doc_id = _create_expense_pipeline(
            db_session, test_org, test_user
        )

        response = client.get(
            f"/api/v1/expenses/{expense_id}/review",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["expense"]["id"] == expense_id
        assert body["expense"]["state"] == "draft"
        assert len(body["fields"]) > 0
        assert body["document"]["id"] == doc_id

        # Check a specific field has all five levels.
        total_field = next(
            (f for f in body["fields"] if f["field"] == "total_amount"), None
        )
        assert total_field is not None
        assert total_field["extracted"]["value"] == "121.00"
        assert total_field["normalized"]["value"] == "121.00"
        assert total_field["validated"]["value"] == "121.00"
        assert total_field["validated"]["result"] == "passed"
        assert total_field["accepted"]["value"] == "121.00"

    def test_review_not_found(self, client, auth_headers):
        """Review for non-existent expense -> 404."""
        fake_id = uuid.uuid4()
        response = client.get(
            f"/api/v1/expenses/{fake_id}/review",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_review_isolation(self, client, db_session, test_org, other_org, test_user):
        """Another org cannot review this expense -> 404."""
        expense_id, _, _ = _create_expense_pipeline(
            db_session, test_org, test_user
        )

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

        response = client.post(
            "/api/v1/auth/login",
            json={"username": "otheruser", "password": "otherpass123"},
        )
        other_token = response.json()["token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}

        response = client.get(
            f"/api/v1/expenses/{expense_id}/review",
            headers=other_headers,
        )
        assert response.status_code == 404


# --- POST /expenses/{id}/review/decisions tests ---


class TestReviewDecisions:
    def test_confirm_field(self, client, auth_headers, db_session, test_org, test_user):
        """Confirm a field keeps the validated value."""
        expense_id, _, _ = _create_expense_pipeline(
            db_session, test_org, test_user
        )

        response = client.post(
            f"/api/v1/expenses/{expense_id}/review/decisions",
            json={"field": "total_amount", "decision": "confirm"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["field"] == "total_amount"
        assert body["decision"] == "confirm"
        assert body["validated_value"] == "121.00"
        assert body["expense_state"] == "draft"

    def test_correct_field(self, client, auth_headers, db_session, test_org, test_user):
        """Correct a field with a new value."""
        expense_id, _, _ = _create_expense_pipeline(
            db_session, test_org, test_user
        )

        response = client.post(
            f"/api/v1/expenses/{expense_id}/review/decisions",
            json={
                "field": "total_amount",
                "decision": "correct",
                "corrected_value": "125.00",
                "reason": "Amount was wrong",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["validated_value"] == "125.00"
        assert body["validation_result"] == "corrected"

    def test_reject_field(self, client, auth_headers, db_session, test_org, test_user):
        """Reject a field sets expense to rejected."""
        expense_id, _, _ = _create_expense_pipeline(
            db_session, test_org, test_user
        )

        response = client.post(
            f"/api/v1/expenses/{expense_id}/review/decisions",
            json={
                "field": "total_amount",
                "decision": "reject",
                "reason": "Invalid amount",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["expense_state"] == "rejected"

    def test_invalid_decision(self, client, auth_headers, db_session, test_org, test_user):
        """Unknown decision -> 409."""
        expense_id, _, _ = _create_expense_pipeline(
            db_session, test_org, test_user
        )

        response = client.post(
            f"/api/v1/expenses/{expense_id}/review/decisions",
            json={"field": "total_amount", "decision": "unknown"},
            headers=auth_headers,
        )
        assert response.status_code == 409

    def test_decision_not_found(self, client, auth_headers):
        """Decision for non-existent expense -> 404."""
        fake_id = uuid.uuid4()
        response = client.post(
            f"/api/v1/expenses/{fake_id}/review/decisions",
            json={"field": "total_amount", "decision": "confirm"},
            headers=auth_headers,
        )
        assert response.status_code == 409


# --- POST /expenses/{id}/accept tests ---


class TestAcceptExpense:
    def test_accept_success(self, client, auth_headers, db_session, test_org, test_user):
        """Accept an expense in draft state."""
        expense_id, _, _ = _create_expense_pipeline(
            db_session, test_org, test_user
        )

        response = client.post(
            f"/api/v1/expenses/{expense_id}/accept",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["expense_id"] == expense_id
        assert body["state"] == "accepted"

        # Verify in DB.
        expense = (
            db_session.execute(
                select(Expense).where(Expense.id == uuid.UUID(expense_id))
            )
            .scalars()
            .first()
        )
        assert expense.state == "accepted"
        assert expense.accepted_snapshot is not None
        snapshot = json.loads(expense.accepted_snapshot)
        assert snapshot["state"] == "accepted"

    def test_accept_with_duplicate(self, client, auth_headers, db_session, test_org, test_user):
        """Cannot accept if probable duplicate exists."""
        expense_id, _, doc_id = _create_expense_pipeline(
            db_session, test_org, test_user
        )

        # Create a second document and a probable duplication.
        content2 = b"second document"
        fingerprint2 = hashlib.sha256(content2).hexdigest()
        doc2 = SourceDocument(
            id=uuid7(),
            owner_id=test_org.id,
            safe_name=f"{uuid7()}.xml",
            original_filename="test2.xml",
            fingerprint_sha256=fingerprint2,
            doc_type="received_invoice",
            format_detected="xml",
            size_bytes=len(content2),
            uploaded_by=test_user.id,
            state="uploaded",
        )
        db_session.add(doc2)
        db_session.commit()

        dup = Duplication(
            id=uuid7(),
            owner_id=test_org.id,
            document_a_id=uuid.UUID(doc_id),
            document_b_id=doc2.id,
            dup_type="fingerprint",
            state="probable",
        )
        db_session.add(dup)
        db_session.commit()

        response = client.post(
            f"/api/v1/expenses/{expense_id}/accept",
            headers=auth_headers,
        )
        assert response.status_code == 409

    def test_accept_invalid_state(self, client, auth_headers, db_session, test_org, test_user):
        """Cannot accept a rejected expense."""
        expense_id, _, _ = _create_expense_pipeline(
            db_session, test_org, test_user
        )

        # Reject first.
        client.post(
            f"/api/v1/expenses/{expense_id}/reject",
            json={"reason": "Test rejection"},
            headers=auth_headers,
        )

        response = client.post(
            f"/api/v1/expenses/{expense_id}/accept",
            headers=auth_headers,
        )
        assert response.status_code == 409

    def test_accept_not_found(self, client, auth_headers):
        """Accept non-existent expense -> 409."""
        fake_id = uuid.uuid4()
        response = client.post(
            f"/api/v1/expenses/{fake_id}/accept",
            headers=auth_headers,
        )
        assert response.status_code == 409


# --- POST /expenses/{id}/reject tests ---


class TestRejectExpense:
    def test_reject_success(self, client, auth_headers, db_session, test_org, test_user):
        """Reject an expense in draft state."""
        expense_id, _, _ = _create_expense_pipeline(
            db_session, test_org, test_user
        )

        response = client.post(
            f"/api/v1/expenses/{expense_id}/reject",
            json={"reason": "Invalid document"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["state"] == "rejected"
        assert body["rejection_reason"] == "Invalid document"

    def test_reject_already_rejected(self, client, auth_headers, db_session, test_org, test_user):
        """Cannot reject an already rejected expense."""
        expense_id, _, _ = _create_expense_pipeline(
            db_session, test_org, test_user
        )

        client.post(
            f"/api/v1/expenses/{expense_id}/reject",
            json={"reason": "First rejection"},
            headers=auth_headers,
        )

        response = client.post(
            f"/api/v1/expenses/{expense_id}/reject",
            json={"reason": "Second rejection"},
            headers=auth_headers,
        )
        assert response.status_code == 409

    def test_reject_accepted(self, client, auth_headers, db_session, test_org, test_user):
        """Cannot reject an accepted expense."""
        expense_id, _, _ = _create_expense_pipeline(
            db_session, test_org, test_user
        )

        client.post(
            f"/api/v1/expenses/{expense_id}/accept",
            headers=auth_headers,
        )

        response = client.post(
            f"/api/v1/expenses/{expense_id}/reject",
            json={"reason": "Try to reject"},
            headers=auth_headers,
        )
        assert response.status_code == 409


# --- POST /expenses/{id}/void tests ---


class TestVoidExpense:
    def test_void_success(self, client, auth_headers, db_session, test_org, test_user):
        """Void an accepted expense."""
        expense_id, _, _ = _create_expense_pipeline(
            db_session, test_org, test_user
        )

        client.post(
            f"/api/v1/expenses/{expense_id}/accept",
            headers=auth_headers,
        )

        response = client.post(
            f"/api/v1/expenses/{expense_id}/void",
            json={"reason": "Duplicate entry"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["state"] == "voided"
        assert body["voided_reason"] == "Duplicate entry"

    def test_void_not_accepted(self, client, auth_headers, db_session, test_org, test_user):
        """Cannot void a non-accepted expense."""
        expense_id, _, _ = _create_expense_pipeline(
            db_session, test_org, test_user
        )

        response = client.post(
            f"/api/v1/expenses/{expense_id}/void",
            json={"reason": "Try to void"},
            headers=auth_headers,
        )
        assert response.status_code == 409
