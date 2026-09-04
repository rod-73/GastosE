"""Tests for V3-S2: Deterministic validation of normalized values.

Covers:
- Unit tests for VR rules (arith, schema, norm, biz).
- POST /extractions/{id}/validate (success, no normalization, not found, isolation, idempotency).
- GET /extractions/{id}/validated-values (list, empty, not found, isolation).
- Document state transitions (validated, validation_error, under_review).
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
)
from backend.main import create_app
from backend.services import validation_service
from backend.services.validation_service import (
    vr_arith_1,
    vr_schema_2,
    vr_norm_1,
    vr_norm_2,
    vr_norm_3,
    vr_norm_4,
    vr_biz_5,
    vr_biz_8,
    vr_biz_9,
    validate_field,
)
from backend.utils import uuid7
import bcrypt


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# --- Unit tests for VR rules ---


class TestVrArith1:
    def test_pass(self):
        values = {
            "total_amount": "121.00",
            "base_amount": "100.00",
            "vat_amount": "21.00",
            "withholding_amount": "0",
        }
        result = vr_arith_1(values)
        assert result.passed is True
        assert result.rule_id == "VR-ARITH-1"

    def test_fail(self):
        values = {
            "total_amount": "150.00",
            "base_amount": "100.00",
            "vat_amount": "21.00",
            "withholding_amount": "0",
        }
        result = vr_arith_1(values)
        assert result.passed is False
        assert result.severity == "BLOCK"

    def test_with_withholding(self):
        values = {
            "total_amount": "110.00",
            "base_amount": "100.00",
            "vat_amount": "21.00",
            "withholding_amount": "11.00",
        }
        result = vr_arith_1(values)
        assert result.passed is True

    def test_tolerance(self):
        # 0.01 tolerance.
        values = {
            "total_amount": "121.01",
            "base_amount": "100.00",
            "vat_amount": "21.00",
            "withholding_amount": "0",
        }
        result = vr_arith_1(values)
        assert result.passed is True


class TestVrSchema2:
    def test_pass(self):
        values = {
            "supplier_name": "Acme",
            "total_amount": "100.00",
            "currency": "EUR",
            "invoice_date": "2024-01-15",
        }
        result = vr_schema_2(values)
        assert result.passed is True

    def test_fail_missing_field(self):
        values = {
            "supplier_name": "Acme",
            "total_amount": "100.00",
            # Missing currency and invoice_date.
        }
        result = vr_schema_2(values)
        assert result.passed is False
        assert "currency" in result.message


class TestVrNorm1:
    def test_valid_currency(self):
        result = vr_norm_1({"currency": "EUR"})
        assert result.passed is True

    def test_invalid_currency(self):
        result = vr_norm_1({"currency": "EURO"})
        assert result.passed is False


class TestVrNorm2:
    def test_valid_date(self):
        result = vr_norm_2({"invoice_date": "2024-01-15"})
        assert result.passed is True

    def test_future_date(self):
        future = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
        result = vr_norm_2({"invoice_date": future})
        assert result.passed is False

    def test_invalid_format(self):
        result = vr_norm_2({"invoice_date": "not-a-date"})
        assert result.passed is False


class TestVrNorm3:
    def test_valid_nif(self):
        result = vr_norm_3({"supplier_nif": "12345678Z"})
        assert result.passed is True

    def test_no_nif(self):
        result = vr_norm_3({})
        assert result.passed is True  # Optional.

    def test_invalid_format(self):
        result = vr_norm_3({"supplier_nif": "INVALID"})
        assert result.passed is False


class TestVrNorm4:
    def test_valid_rate(self):
        result = vr_norm_4({"vat_rate": "21"})
        assert result.passed is True

    def test_unknown_rate(self):
        result = vr_norm_4({"vat_rate": "15"})
        assert result.passed is False

    def test_no_rate(self):
        result = vr_norm_4({})
        assert result.passed is True  # Optional.


class TestVrBiz9:
    def test_reasonable(self):
        result = vr_biz_9({"total_amount": "100.00"})
        assert result.passed is True

    def test_too_large(self):
        result = vr_biz_9({"total_amount": "2000000.00"})
        assert result.passed is False
        assert result.severity == "WARN"

    def test_negative(self):
        result = vr_biz_9({"total_amount": "-5.00"})
        assert result.passed is False


class TestValidateField:
    def test_passed(self):
        values = {
            "supplier_name": "Acme",
            "total_amount": "121.00",
            "base_amount": "100.00",
            "vat_amount": "21.00",
            "currency": "EUR",
            "invoice_date": "2024-01-15",
            "vat_rate": "21",
        }
        result = validate_field("total_amount", "121.00", values)
        assert result.overall_result == "passed"

    def test_failed(self):
        values = {
            "supplier_name": "Acme",
            "total_amount": "999.00",
            "base_amount": "100.00",
            "vat_amount": "21.00",
            "currency": "EUR",
            "invoice_date": "2024-01-15",
        }
        result = validate_field("total_amount", "999.00", values)
        assert result.overall_result == "failed"


# --- Integration tests (API endpoints) ---


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


def _create_normalized_extraction(
    db: DbSession,
    org: Organization,
    user: User,
    values: list[dict] | None = None,
) -> tuple[SourceDocument, Extraction]:
    """Create a document + completed extraction + normalized values."""
    if values is None:
        values = [
            {"field": "supplier_name", "raw_value": "Acme Corp SL", "normalized": "Acme Corp SL"},
            {"field": "total_amount", "raw_value": "121.00", "normalized": "121.00"},
            {"field": "base_amount", "raw_value": "100.00", "normalized": "100.00"},
            {"field": "vat_amount", "raw_value": "21.00", "normalized": "21.00"},
            {"field": "currency", "raw_value": "EUR", "normalized": "EUR"},
            {"field": "invoice_date", "raw_value": "2024-01-15", "normalized": "2024-01-15"},
            {"field": "vat_rate", "raw_value": "21%", "normalized": "21"},
        ]

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
            raw_value=v["raw_value"],
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
            normalized_value=v["normalized"],
            normalization_rule="test_rule",
        )
        db.add(nv)

    db.commit()
    db.refresh(doc)
    db.refresh(extraction)

    from backend.config import get_settings
    settings = get_settings()
    directory = os.path.join(settings.DOCUMENT_STORAGE_PATH, str(org.id))
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, fingerprint)
    with open(path, "wb") as fh:
        fh.write(content)

    return doc, extraction


def _create_extraction_without_normalization(
    db: DbSession,
    org: Organization,
    user: User,
) -> tuple[SourceDocument, Extraction]:
    """Create a document + completed extraction WITHOUT normalized values."""
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
        state="extracted",
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

    ev = ExtractedValue(
        id=uuid7(),
        owner_id=org.id,
        extraction_id=extraction.id,
        field="supplier_name",
        raw_value="Acme",
        confidence=0.95,
        provenance={"method": "xml_schema", "rule": "xml:supplier_name"},
    )
    db.add(ev)
    db.commit()
    db.refresh(doc)
    db.refresh(extraction)

    from backend.config import get_settings
    settings = get_settings()
    directory = os.path.join(settings.DOCUMENT_STORAGE_PATH, str(org.id))
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, fingerprint)
    with open(path, "wb") as fh:
        fh.write(content)

    return doc, extraction


# --- POST /extractions/{id}/validate tests ---


class TestValidateEndpoint:
    def test_validate_success(self, client, auth_headers, db_session, test_org, test_user):
        """Validation of a normalized extraction with valid values."""
        doc, extraction = _create_normalized_extraction(
            db_session, test_org, test_user
        )

        response = client.post(
            f"/api/v1/extractions/{extraction.id}/validate",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["extraction_id"] == str(extraction.id)
        assert body["failed_count"] == 0
        assert body["document_state"] == "validated"

    def test_validate_with_arithmetic_failure(self, client, auth_headers, db_session, test_org, test_user):
        """Validation with inconsistent amounts -> validation_error."""
        values = [
            {"field": "supplier_name", "raw_value": "Acme", "normalized": "Acme"},
            {"field": "total_amount", "raw_value": "999.00", "normalized": "999.00"},
            {"field": "base_amount", "raw_value": "100.00", "normalized": "100.00"},
            {"field": "vat_amount", "raw_value": "21.00", "normalized": "21.00"},
            {"field": "currency", "raw_value": "EUR", "normalized": "EUR"},
            {"field": "invoice_date", "raw_value": "2024-01-15", "normalized": "2024-01-15"},
        ]
        doc, extraction = _create_normalized_extraction(
            db_session, test_org, test_user, values=values
        )

        response = client.post(
            f"/api/v1/extractions/{extraction.id}/validate",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["failed_count"] > 0
        assert body["document_state"] == "validation_error"

    def test_validate_without_normalization(self, client, auth_headers, db_session, test_org, test_user):
        """Validation without normalized values -> 409."""
        doc, extraction = _create_extraction_without_normalization(
            db_session, test_org, test_user
        )

        response = client.post(
            f"/api/v1/extractions/{extraction.id}/validate",
            headers=auth_headers,
        )
        assert response.status_code == 409

    def test_validate_not_found(self, client, auth_headers):
        """Validation of a non-existent extraction -> 404."""
        fake_id = uuid.uuid4()
        response = client.post(
            f"/api/v1/extractions/{fake_id}/validate",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_validate_isolation(self, client, db_session, test_org, other_org, test_user):
        """Another org cannot validate this extraction -> 404."""
        doc, extraction = _create_normalized_extraction(
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
            f"/api/v1/extractions/{extraction.id}/validate",
            headers=other_headers,
        )
        assert response.status_code == 404

    def test_validate_idempotency(self, client, auth_headers, db_session, test_org, test_user):
        """Calling validate twice returns the same result without duplicates."""
        doc, extraction = _create_normalized_extraction(
            db_session, test_org, test_user
        )

        response1 = client.post(
            f"/api/v1/extractions/{extraction.id}/validate",
            headers=auth_headers,
        )
        assert response1.status_code == 200
        body1 = response1.json()

        response2 = client.post(
            f"/api/v1/extractions/{extraction.id}/validate",
            headers=auth_headers,
        )
        assert response2.status_code == 200
        body2 = response2.json()
        assert body1["passed_count"] == body2["passed_count"]
        assert body1["failed_count"] == body2["failed_count"]

        # Verify no duplicates in DB.
        count = len(
            db_session.execute(
                select(ValidatedValue).where(
                    ValidatedValue.normalized_value_id.in_(
                        select(NormalizedValue.id).where(
                            NormalizedValue.extracted_value_id.in_(
                                select(ExtractedValue.id).where(
                                    ExtractedValue.extraction_id == extraction.id
                                )
                            )
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        # Should equal the number of normalized values (7).
        assert count == 7


# --- GET /extractions/{id}/validated-values tests ---


class TestValidatedValuesEndpoint:
    def test_list_validated_values(self, client, auth_headers, db_session, test_org, test_user):
        """List validated values after validation."""
        doc, extraction = _create_normalized_extraction(
            db_session, test_org, test_user
        )

        client.post(
            f"/api/v1/extractions/{extraction.id}/validate",
            headers=auth_headers,
        )

        response = client.get(
            f"/api/v1/extractions/{extraction.id}/validated-values",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["extraction_id"] == str(extraction.id)
        assert body["count"] == 7
        assert len(body["values"]) == 7

        # Verify specific validated values.
        fields = {v["field"]: v for v in body["values"]}
        assert fields["total_amount"]["validated_value"] == "121.00"
        assert fields["currency"]["validated_value"] == "EUR"

    def test_list_empty(self, client, auth_headers, db_session, test_org, test_user):
        """List validated values before validation -> empty."""
        doc, extraction = _create_normalized_extraction(
            db_session, test_org, test_user
        )

        response = client.get(
            f"/api/v1/extractions/{extraction.id}/validated-values",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 0

    def test_list_not_found(self, client, auth_headers):
        """List validated values for non-existent extraction -> 404."""
        fake_id = uuid.uuid4()
        response = client.get(
            f"/api/v1/extractions/{fake_id}/validated-values",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_list_isolation(self, client, db_session, test_org, other_org, test_user):
        """Another org cannot list validated values -> 404."""
        doc, extraction = _create_normalized_extraction(
            db_session, test_org, test_user
        )

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
        assert response.status_code == 200
        other_token = response.json()["token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}

        response = client.get(
            f"/api/v1/extractions/{extraction.id}/validated-values",
            headers=other_headers,
        )
        assert response.status_code == 404

    def test_validated_value_provenance(self, client, auth_headers, db_session, test_org, test_user):
        """Validated values reference the normalized value (INV-10)."""
        doc, extraction = _create_normalized_extraction(
            db_session, test_org, test_user
        )

        client.post(
            f"/api/v1/extractions/{extraction.id}/validate",
            headers=auth_headers,
        )

        vvs = (
            db_session.execute(
                select(ValidatedValue).where(
                    ValidatedValue.normalized_value_id.in_(
                        select(NormalizedValue.id).where(
                            NormalizedValue.extracted_value_id.in_(
                                select(ExtractedValue.id).where(
                                    ExtractedValue.extraction_id == extraction.id
                                )
                            )
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(vvs) == 7
        for vv in vvs:
            assert vv.normalized_value_id is not None
            assert vv.owner_id == test_org.id
            assert vv.rules_applied is not None
            # rules_applied should be valid JSON.
            rules = json.loads(vv.rules_applied)
            assert isinstance(rules, list)
