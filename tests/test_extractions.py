"""Tests for V2-S2: Extraction retry, list, and detail endpoints.

Covers:
- POST /documents/{id}/extractions/retry (success, wrong state, active job).
- GET /documents/{id}/extractions (list, empty, isolation).
- GET /extractions/{id} (detail with values, not found, isolation).
"""
from __future__ import annotations

import hashlib
import os
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
    SourceDocument,
    ExtractionJob,
    Extraction,
    ExtractedValue,
)
from backend.main import create_app
from backend.utils import uuid7
import bcrypt


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


XML_INVOICE = b"""<?xml version="1.0" encoding="UTF-8"?>
<Facturae xmlns="urn:es:febom:facturae:3.2">
  <Emisor>
    <Nombre>Acme Corp SL</Nombre>
    <NIF>A12345678</NIF>
  </Emisor>
  <Referencia>INV-2024-001</Referencia>
  <FechaEmision>2024-01-15</FechaEmision>
  <ImporteTotal>121.00</ImporteTotal>
  <BaseImponible>100.00</BaseImponible>
  <Tipo>21</Tipo>
  <Cuota>21.00</Cuota>
  <Moneda>EUR</Moneda>
</Facturae>
"""


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


def _create_failed_document(
    db: DbSession,
    org: Organization,
    user: User,
    content: bytes = b"\xff\xd8\xff\xe0 jpeg",
    format_detected: str = "pdf_scanned",
) -> SourceDocument:
    """Create a document in 'failed' state with a failed job."""
    fingerprint = hashlib.sha256(content).hexdigest()
    safe_name = f"{uuid7()}.jpg"

    doc = SourceDocument(
        id=uuid7(),
        owner_id=org.id,
        safe_name=safe_name,
        original_filename="test.jpg",
        fingerprint_sha256=fingerprint,
        doc_type="received_invoice",
        format_detected=format_detected,
        size_bytes=len(content),
        uploaded_by=user.id,
        state="failed",
        failure_reason="OCR extraction not implemented",
    )
    db.add(doc)
    db.flush()

    job = ExtractionJob(
        id=uuid7(),
        owner_id=org.id,
        document_id=doc.id,
        document_fingerprint=fingerprint,
        format_detected=format_detected,
        state="failed",
        attempts=3,
        max_attempts=3,
        failure_reason="OCR extraction not implemented",
        failure_code="extraction_error",
    )
    db.add(job)
    db.commit()
    db.refresh(doc)

    # Store the file.
    from backend.config import get_settings
    settings = get_settings()
    directory = os.path.join(settings.DOCUMENT_STORAGE_PATH, str(org.id))
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, fingerprint)
    with open(path, "wb") as fh:
        fh.write(content)

    return doc


def _create_completed_extraction(
    db: DbSession,
    org: Organization,
    doc: SourceDocument,
) -> Extraction:
    """Create a completed extraction with values."""
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
        ExtractedValue(
            id=uuid7(),
            owner_id=org.id,
            extraction_id=extraction.id,
            field="supplier_name",
            raw_value="Acme Corp SL",
            confidence=0.98,
            provenance={"method": "xml_schema", "rule": "xml:Emisor/Nombre"},
        ),
        ExtractedValue(
            id=uuid7(),
            owner_id=org.id,
            extraction_id=extraction.id,
            field="total_amount",
            raw_value="121.00",
            confidence=0.99,
            provenance={"method": "xml_schema", "rule": "xml:ImporteTotal"},
        ),
    ]
    for v in values:
        db.add(v)

    db.commit()
    db.refresh(extraction)
    return extraction


# === Test: Retry endpoint ===


class TestRetry:
    def test_retry_failed_document(self, client, auth_headers, db_session, test_org, test_user):
        doc = _create_failed_document(db_session, test_org, test_user)

        response = client.post(
            f"/api/v1/documents/{doc.id}/extractions/retry",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["document_id"] == str(doc.id)
        assert body["state"] == "pending"
        assert "job_id" in body

        # Verify a new job was created.
        jobs = (
            db_session.execute(
                select(ExtractionJob).where(
                    ExtractionJob.document_id == doc.id,
                    ExtractionJob.state == "pending",
                )
            )
            .scalars()
            .all()
        )
        assert len(jobs) == 1

        # Verify document state was reset.
        db_session.refresh(doc)
        assert doc.state == "uploaded"
        assert doc.failure_reason is None

    def test_retry_not_failed(self, client, auth_headers, db_session, test_org, test_user):
        """Retry should fail if the document is not in 'failed' state."""
        # Create a document in 'uploaded' state.
        fingerprint = hashlib.sha256(XML_INVOICE).hexdigest()
        doc = SourceDocument(
            id=uuid7(),
            owner_id=test_org.id,
            safe_name=f"{uuid7()}.xml",
            original_filename="test.xml",
            fingerprint_sha256=fingerprint,
            doc_type="received_invoice",
            format_detected="xml",
            size_bytes=len(XML_INVOICE),
            uploaded_by=test_user.id,
            state="uploaded",
        )
        db_session.add(doc)
        db_session.commit()

        response = client.post(
            f"/api/v1/documents/{doc.id}/extractions/retry",
            headers=auth_headers,
        )
        assert response.status_code == 409

    def test_retry_with_active_job(self, client, auth_headers, db_session, test_org, test_user):
        """Retry should fail if there's already a pending/running job."""
        doc = _create_failed_document(db_session, test_org, test_user)

        # Create a pending job.
        job = ExtractionJob(
            id=uuid7(),
            owner_id=test_org.id,
            document_id=doc.id,
            document_fingerprint=doc.fingerprint_sha256,
            format_detected=doc.format_detected,
            state="pending",
        )
        db_session.add(job)
        db_session.commit()

        response = client.post(
            f"/api/v1/documents/{doc.id}/extractions/retry",
            headers=auth_headers,
        )
        assert response.status_code == 409

    def test_retry_not_found(self, client, auth_headers):
        fake_id = uuid.uuid4()
        response = client.post(
            f"/api/v1/documents/{fake_id}/extractions/retry",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_retry_isolation(self, client, auth_headers, db_session, other_org, test_user):
        """Cannot retry a document from another org."""
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

        doc = _create_failed_document(db_session, other_org, other_user)

        response = client.post(
            f"/api/v1/documents/{doc.id}/extractions/retry",
            headers=auth_headers,
        )
        assert response.status_code == 404


# === Test: List extractions ===


class TestListExtractions:
    def test_list_with_extractions(self, client, auth_headers, db_session, test_org, test_user):
        # Create a document.
        fingerprint = hashlib.sha256(XML_INVOICE).hexdigest()
        doc = SourceDocument(
            id=uuid7(),
            owner_id=test_org.id,
            safe_name=f"{uuid7()}.xml",
            original_filename="test.xml",
            fingerprint_sha256=fingerprint,
            doc_type="received_invoice",
            format_detected="xml",
            size_bytes=len(XML_INVOICE),
            uploaded_by=test_user.id,
            state="extracted",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        # Create two extractions.
        ext1 = _create_completed_extraction(db_session, test_org, doc)
        ext2 = Extraction(
            id=uuid7(),
            owner_id=test_org.id,
            document_id=doc.id,
            method="pdf_text_rules",
            state="failed",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            failure_reason="No fields found",
        )
        db_session.add(ext2)
        db_session.commit()

        response = client.get(
            f"/api/v1/documents/{doc.id}/extractions",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["document_id"] == str(doc.id)
        assert body["count"] == 2
        assert len(body["extractions"]) == 2

    def test_list_empty(self, client, auth_headers, db_session, test_org, test_user):
        fingerprint = hashlib.sha256(XML_INVOICE).hexdigest()
        doc = SourceDocument(
            id=uuid7(),
            owner_id=test_org.id,
            safe_name=f"{uuid7()}.xml",
            original_filename="test.xml",
            fingerprint_sha256=fingerprint,
            doc_type="received_invoice",
            format_detected="xml",
            size_bytes=len(XML_INVOICE),
            uploaded_by=test_user.id,
            state="uploaded",
        )
        db_session.add(doc)
        db_session.commit()

        response = client.get(
            f"/api/v1/documents/{doc.id}/extractions",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 0
        assert body["extractions"] == []

    def test_list_not_found(self, client, auth_headers):
        fake_id = uuid.uuid4()
        response = client.get(
            f"/api/v1/documents/{fake_id}/extractions",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_list_isolation(self, client, auth_headers, db_session, other_org, test_user):
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

        fingerprint = hashlib.sha256(XML_INVOICE).hexdigest()
        doc = SourceDocument(
            id=uuid7(),
            owner_id=other_org.id,
            safe_name=f"{uuid7()}.xml",
            original_filename="test.xml",
            fingerprint_sha256=fingerprint,
            doc_type="received_invoice",
            format_detected="xml",
            size_bytes=len(XML_INVOICE),
            uploaded_by=other_user.id,
            state="extracted",
        )
        db_session.add(doc)
        db_session.commit()

        response = client.get(
            f"/api/v1/documents/{doc.id}/extractions",
            headers=auth_headers,
        )
        assert response.status_code == 404


# === Test: Get extraction detail ===


class TestGetExtraction:
    def test_get_with_values(self, client, auth_headers, db_session, test_org, test_user):
        fingerprint = hashlib.sha256(XML_INVOICE).hexdigest()
        doc = SourceDocument(
            id=uuid7(),
            owner_id=test_org.id,
            safe_name=f"{uuid7()}.xml",
            original_filename="test.xml",
            fingerprint_sha256=fingerprint,
            doc_type="received_invoice",
            format_detected="xml",
            size_bytes=len(XML_INVOICE),
            uploaded_by=test_user.id,
            state="extracted",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        ext = _create_completed_extraction(db_session, test_org, doc)

        response = client.get(
            f"/api/v1/extractions/{ext.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(ext.id)
        assert body["method"] == "xml_schema"
        assert body["state"] == "completed"
        assert len(body["values"]) == 2

        # Check values.
        fields = {v["field"] for v in body["values"]}
        assert "supplier_name" in fields
        assert "total_amount" in fields

        # Check confidence and provenance.
        for v in body["values"]:
            assert 0 <= v["confidence"] <= 1
            assert "method" in v["provenance"]

    def test_get_failed_extraction(self, client, auth_headers, db_session, test_org, test_user):
        fingerprint = hashlib.sha256(b"test").hexdigest()
        doc = SourceDocument(
            id=uuid7(),
            owner_id=test_org.id,
            safe_name=f"{uuid7()}.jpg",
            original_filename="test.jpg",
            fingerprint_sha256=fingerprint,
            doc_type="received_invoice",
            format_detected="pdf_scanned",
            size_bytes=4,
            uploaded_by=test_user.id,
            state="failed",
            failure_reason="OCR not implemented",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        ext = Extraction(
            id=uuid7(),
            owner_id=test_org.id,
            document_id=doc.id,
            method="ocr",
            state="failed",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            failure_reason="OCR not implemented",
        )
        db_session.add(ext)
        db_session.commit()
        db_session.refresh(ext)

        response = client.get(
            f"/api/v1/extractions/{ext.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["state"] == "failed"
        assert body["failure_reason"] == "OCR not implemented"
        assert body["values"] == []

    def test_get_not_found(self, client, auth_headers):
        fake_id = uuid.uuid4()
        response = client.get(
            f"/api/v1/extractions/{fake_id}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_get_isolation(self, client, auth_headers, db_session, other_org, test_user):
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

        fingerprint = hashlib.sha256(XML_INVOICE).hexdigest()
        doc = SourceDocument(
            id=uuid7(),
            owner_id=other_org.id,
            safe_name=f"{uuid7()}.xml",
            original_filename="test.xml",
            fingerprint_sha256=fingerprint,
            doc_type="received_invoice",
            format_detected="xml",
            size_bytes=len(XML_INVOICE),
            uploaded_by=other_user.id,
            state="extracted",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        ext = _create_completed_extraction(db_session, other_org, doc)

        response = client.get(
            f"/api/v1/extractions/{ext.id}",
            headers=auth_headers,
        )
        assert response.status_code == 404
