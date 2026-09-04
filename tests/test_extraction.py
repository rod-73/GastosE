"""Tests for V2-S1: Extraction worker (claim, process, validate, persist).

Covers:
- Worker claim endpoint (atomic claim, FIFO, no pending jobs).
- Worker process endpoint (XML extraction, PDF text extraction, failure).
- Schema validation (valid, invalid, missing required fields).
- Idempotency (re-claim after completed extraction).
- Retry with backoff.
- Lease expiry / reaping.
- Isolation (org A cannot access org B's jobs).
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


# --- Test XML content (Facturae-like) ---
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

# --- Test XML content (generic) ---
XML_GENERIC = b"""<?xml version="1.0"?>
<invoice>
  <supplier>Test Supplier Ltd</supplier>
  <nif>B98765432</nif>
  <invoicenumber>GEN-0042</invoicenumber>
  <date>2024-06-01</date>
  <total>500.00</total>
  <baseamount>413.22</baseamount>
  <vatrate>21</vatrate>
  <vatamount>86.78</vatamount>
  <currency>EUR</currency>
</invoice>
"""

# --- Test PDF text content (simulated text layer) ---
PDF_TEXT_CONTENT = b"""Supplier: Beta Industries
NIF: C11223344
Invoice No: PDF-2024-007
Date: 2024-03-20
Total: 250.00
Base: 206.61
IVA: 21%
VAT: 43.39
Currency: EUR
"""


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_path, monkeypatch):
    """Redirect document storage to a temp dir for every test."""
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
    assert response.status_code == 200, f"Login failed: {response.text}"
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _create_document_with_job(
    db: DbSession,
    org: Organization,
    user: User,
    content: bytes,
    format_detected: str,
) -> tuple[SourceDocument, ExtractionJob]:
    """Helper: create a document + job in the DB and store the file."""
    fingerprint = hashlib.sha256(content).hexdigest()
    safe_name = f"{uuid7()}.xml" if format_detected == "xml" else f"{uuid7()}.pdf"

    doc = SourceDocument(
        id=uuid7(),
        owner_id=org.id,
        safe_name=safe_name,
        original_filename="test.xml" if format_detected == "xml" else "test.pdf",
        fingerprint_sha256=fingerprint,
        doc_type="received_invoice",
        format_detected=format_detected,
        size_bytes=len(content),
        page_count=None,
        uploaded_by=user.id,
        state="uploaded",
    )
    db.add(doc)
    db.flush()

    job = ExtractionJob(
        id=uuid7(),
        owner_id=org.id,
        document_id=doc.id,
        document_fingerprint=fingerprint,
        format_detected=format_detected,
        state="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(doc)
    db.refresh(job)

    # Store the file.
    from backend.config import get_settings
    settings = get_settings()
    directory = os.path.join(settings.DOCUMENT_STORAGE_PATH, str(org.id))
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, fingerprint)
    with open(path, "wb") as fh:
        fh.write(content)

    return doc, job


# === Test: Schema validation ===


class TestSchemaValidation:
    def test_valid_extraction_output(self):
        from backend.services.extraction_schema import validate_extraction_output

        output = {
            "supplier_name": {
                "raw_value": "Acme Corp",
                "confidence": 0.95,
                "provenance": {"method": "xml_schema", "rule": "xml:Emisor/Nombre"},
            },
            "total_amount": {
                "raw_value": "100.00",
                "confidence": 0.99,
                "provenance": {"method": "xml_schema", "rule": "xml:ImporteTotal"},
            },
        }
        result = validate_extraction_output(output, "xml_schema")
        assert result.is_valid
        assert len(result.fields) == 2

    def test_missing_required_field(self):
        from backend.services.extraction_schema import validate_extraction_output

        output = {
            "supplier_name": {
                "raw_value": "Acme Corp",
                "confidence": 0.95,
                "provenance": {"method": "xml_schema"},
            },
            # total_amount missing
        }
        result = validate_extraction_output(output, "xml_schema")
        assert not result.is_valid
        assert any("total_amount" in e for e in result.errors)

    def test_unknown_field(self):
        from backend.services.extraction_schema import validate_extraction_output

        output = {
            "supplier_name": {
                "raw_value": "Acme",
                "confidence": 0.9,
                "provenance": {"method": "xml_schema"},
            },
            "total_amount": {
                "raw_value": "100",
                "confidence": 0.9,
                "provenance": {"method": "xml_schema"},
            },
            "unknown_field": {
                "raw_value": "x",
                "confidence": 0.5,
                "provenance": {"method": "xml_schema"},
            },
        }
        result = validate_extraction_output(output, "xml_schema")
        assert not result.is_valid
        assert any("Unknown field" in e for e in result.errors)

    def test_invalid_confidence(self):
        from backend.services.extraction_schema import validate_extraction_output

        output = {
            "supplier_name": {
                "raw_value": "Acme",
                "confidence": 1.5,  # > 1
                "provenance": {"method": "xml_schema"},
            },
            "total_amount": {
                "raw_value": "100",
                "confidence": 0.9,
                "provenance": {"method": "xml_schema"},
            },
        }
        result = validate_extraction_output(output, "xml_schema")
        assert not result.is_valid

    def test_empty_required_field(self):
        from backend.services.extraction_schema import validate_extraction_output

        output = {
            "supplier_name": {
                "raw_value": "",  # empty
                "confidence": 0.9,
                "provenance": {"method": "xml_schema"},
            },
            "total_amount": {
                "raw_value": "100",
                "confidence": 0.9,
                "provenance": {"method": "xml_schema"},
            },
        }
        result = validate_extraction_output(output, "xml_schema")
        assert not result.is_valid

    def test_error_output_fails_validation(self):
        from backend.services.extraction_schema import validate_extraction_output

        output = {"_error": "Something went wrong"}
        result = validate_extraction_output(output, "xml_schema")
        assert not result.is_valid


# === Test: Extraction methods ===


class TestExtractionMethods:
    def test_xml_facturae_extraction(self):
        from backend.services.extraction_methods import extract_xml

        result = extract_xml(XML_INVOICE)
        assert "_error" not in result
        assert "supplier_name" in result
        assert result["supplier_name"]["raw_value"] == "Acme Corp SL"
        assert result["supplier_name"]["confidence"] >= 0.9
        assert "total_amount" in result
        assert result["total_amount"]["raw_value"] == "121.00"

    def test_xml_generic_extraction(self):
        from backend.services.extraction_methods import extract_xml

        result = extract_xml(XML_GENERIC)
        assert "_error" not in result
        assert "supplier_name" in result
        assert result["supplier_name"]["raw_value"] == "Test Supplier Ltd"
        assert "total_amount" in result
        assert result["total_amount"]["raw_value"] == "500.00"

    def test_xml_invalid_content(self):
        from backend.services.extraction_methods import extract_xml

        result = extract_xml(b"not xml at all")
        assert "_error" in result

    def test_pdf_text_extraction(self):
        from backend.services.extraction_methods import extract_pdf_text

        result = extract_pdf_text(PDF_TEXT_CONTENT)
        assert "_error" not in result
        assert "supplier_name" in result
        assert result["supplier_name"]["raw_value"] == "Beta Industries"
        assert "total_amount" in result
        assert result["total_amount"]["raw_value"] == "250.00"

    def test_pdf_binary_content_fails(self):
        from backend.services.extraction_methods import extract_pdf_text

        # Actual PDF binary (starts with %PDF-) should fail without a PDF lib.
        result = extract_pdf_text(b"%PDF-1.4 binary content")
        assert "_error" in result

    def test_ocr_stub_fails(self):
        from backend.services.extraction_methods import extract_ocr

        result = extract_ocr(b"image data")
        assert "_error" in result

    def test_llm_stub_fails(self):
        from backend.services.extraction_methods import extract_llm

        result = extract_llm(b"image data")
        assert "_error" in result


# === Test: Worker claim endpoint ===


class TestWorkerClaim:
    def test_claim_no_pending_jobs(self, client, auth_headers):
        response = client.post("/api/v1/worker/claim", headers=auth_headers)
        assert response.status_code == 404

    def test_claim_pending_job(self, client, auth_headers, db_session, test_org, test_user):
        doc, job = _create_document_with_job(
            db_session, test_org, test_user, XML_INVOICE, "xml"
        )
        response = client.post("/api/v1/worker/claim", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["job_id"] == str(job.id)
        assert body["document_id"] == str(doc.id)
        assert body["format_detected"] == "xml"
        assert body["attempts"] == 1

    def test_claim_fifo_order(self, client, auth_headers, db_session, test_org, test_user):
        """Jobs are claimed in FIFO order (by created_at)."""
        doc1, job1 = _create_document_with_job(
            db_session, test_org, test_user, XML_INVOICE, "xml"
        )
        # Create a second job with a later timestamp.
        doc2 = SourceDocument(
            id=uuid7(),
            owner_id=test_org.id,
            safe_name=f"{uuid7()}.xml",
            original_filename="test2.xml",
            fingerprint_sha256=hashlib.sha256(b"other xml").hexdigest(),
            doc_type="received_invoice",
            format_detected="xml",
            size_bytes=9,
            uploaded_by=test_user.id,
            state="uploaded",
        )
        db_session.add(doc2)
        db_session.flush()
        job2 = ExtractionJob(
            id=uuid7(),
            owner_id=test_org.id,
            document_id=doc2.id,
            document_fingerprint=doc2.fingerprint_sha256,
            format_detected="xml",
            state="pending",
        )
        db_session.add(job2)
        db_session.commit()

        # First claim should get job1 (earlier created_at).
        response = client.post("/api/v1/worker/claim", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["job_id"] == str(job1.id)

    def test_claim_isolation(self, client, auth_headers, db_session, other_org, test_user):
        """Jobs from another org are not visible."""
        # Create a user in the other org.
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

        # Create a job in the other org.
        doc, job = _create_document_with_job(
            db_session, other_org, other_user, XML_INVOICE, "xml"
        )

        # The test user (different org) should not see this job.
        response = client.post("/api/v1/worker/claim", headers=auth_headers)
        assert response.status_code == 404  # No pending jobs for this org.


# === Test: Worker process endpoint ===


class TestWorkerProcess:
    def test_process_xml_job_success(self, client, auth_headers, db_session, test_org, test_user):
        doc, job = _create_document_with_job(
            db_session, test_org, test_user, XML_INVOICE, "xml"
        )

        # Claim the job.
        claim_resp = client.post("/api/v1/worker/claim", headers=auth_headers)
        assert claim_resp.status_code == 200
        job_id = claim_resp.json()["job_id"]

        # Process the job.
        process_resp = client.post(
            f"/api/v1/worker/process?job_id={job_id}",
            headers=auth_headers,
        )
        assert process_resp.status_code == 200
        body = process_resp.json()
        assert body["state"] == "completed"
        assert body["method"] == "xml_schema"
        assert body["fields_extracted"] >= 2
        assert body["failure_code"] is None

        # Verify extraction was persisted.
        extraction = (
            db_session.execute(
                select(Extraction).where(Extraction.id == uuid.UUID(body["extraction_id"]))
            )
            .scalars()
            .first()
        )
        assert extraction is not None
        assert extraction.state == "completed"
        assert extraction.method == "xml_schema"

        # Verify extracted values.
        values = (
            db_session.execute(
                select(ExtractedValue).where(
                    ExtractedValue.extraction_id == extraction.id
                )
            )
            .scalars()
            .all()
        )
        assert len(values) >= 2
        fields = {v.field for v in values}
        assert "supplier_name" in fields
        assert "total_amount" in fields

        # Verify confidence and provenance (INV-11).
        for v in values:
            assert v.confidence is not None
            assert 0 <= float(v.confidence) <= 1
            assert v.provenance is not None
            assert "method" in v.provenance

    def test_process_pdf_text_job_success(self, client, auth_headers, db_session, test_org, test_user):
        doc, job = _create_document_with_job(
            db_session, test_org, test_user, PDF_TEXT_CONTENT, "pdf_text"
        )

        claim_resp = client.post("/api/v1/worker/claim", headers=auth_headers)
        assert claim_resp.status_code == 200
        job_id = claim_resp.json()["job_id"]

        process_resp = client.post(
            f"/api/v1/worker/process?job_id={job_id}",
            headers=auth_headers,
        )
        assert process_resp.status_code == 200
        body = process_resp.json()
        assert body["state"] == "completed"
        assert body["method"] == "pdf_text_rules"
        assert body["fields_extracted"] >= 2

    def test_process_ocr_job_fails(self, client, auth_headers, db_session, test_org, test_user):
        """OCR is not implemented: job should fail."""
        doc, job = _create_document_with_job(
            db_session, test_org, test_user, b"\xff\xd8\xff\xe0 jpeg", "pdf_scanned"
        )

        claim_resp = client.post("/api/v1/worker/claim", headers=auth_headers)
        assert claim_resp.status_code == 200
        job_id = claim_resp.json()["job_id"]

        process_resp = client.post(
            f"/api/v1/worker/process?job_id={job_id}",
            headers=auth_headers,
        )
        assert process_resp.status_code == 200
        body = process_resp.json()
        assert body["state"] == "failed"
        assert body["failure_code"] is not None

    def test_process_not_found(self, client, auth_headers):
        fake_id = uuid.uuid4()
        response = client.post(
            f"/api/v1/worker/process?job_id={fake_id}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_process_wrong_state(self, client, auth_headers, db_session, test_org, test_user):
        """Processing a job that is not in 'running' state returns 409."""
        doc, job = _create_document_with_job(
            db_session, test_org, test_user, XML_INVOICE, "xml"
        )
        # Job is still 'pending' (not claimed).
        response = client.post(
            f"/api/v1/worker/process?job_id={job.id}",
            headers=auth_headers,
        )
        assert response.status_code == 409

    def test_process_wrong_worker(self, client, auth_headers, db_session, test_org, test_user):
        """A different worker cannot process a job claimed by another."""
        doc, job = _create_document_with_job(
            db_session, test_org, test_user, XML_INVOICE, "xml"
        )

        # Claim as test_user.
        claim_resp = client.post("/api/v1/worker/claim", headers=auth_headers)
        assert claim_resp.status_code == 200
        job_id = claim_resp.json()["job_id"]

        # Now create a second user in the same org and try to process.
        other_user = User(
            id=uuid.uuid4(),
            organization_id=test_org.id,
            username="otherworker",
            email="otherworker@example.com",
            password_hash=_hash_password("otherpass456"),
            role="reader",
            state="active",
        )
        db_session.add(other_user)
        db_session.commit()
        db_session.refresh(other_user)

        # Login as the other user.
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"username": "otherworker", "password": "otherpass456"},
        )
        assert login_resp.status_code == 200
        other_token = login_resp.json()["token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}

        # Try to process the job (claimed by test_user).
        response = client.post(
            f"/api/v1/worker/process?job_id={job_id}",
            headers=other_headers,
        )
        assert response.status_code == 403


# === Test: Idempotency ===


class TestIdempotency:
    def test_reprocess_after_completed(self, client, auth_headers, db_session, test_org, test_user):
        """If a completed extraction exists, re-processing is idempotent."""
        doc, job = _create_document_with_job(
            db_session, test_org, test_user, XML_INVOICE, "xml"
        )

        # First claim + process.
        claim1 = client.post("/api/v1/worker/claim", headers=auth_headers)
        assert claim1.status_code == 200
        job_id = claim1.json()["job_id"]

        process1 = client.post(
            f"/api/v1/worker/process?job_id={job_id}",
            headers=auth_headers,
        )
        assert process1.status_code == 200
        assert process1.json()["state"] == "completed"
        extraction_id_1 = process1.json()["extraction_id"]

        # Create a new job for the same document (simulating retry).
        job2 = ExtractionJob(
            id=uuid7(),
            owner_id=test_org.id,
            document_id=doc.id,
            document_fingerprint=doc.fingerprint_sha256,
            format_detected="xml",
            state="pending",
        )
        db_session.add(job2)
        db_session.commit()

        # Claim and process the second job.
        claim2 = client.post("/api/v1/worker/claim", headers=auth_headers)
        assert claim2.status_code == 200
        job_id_2 = claim2.json()["job_id"]

        process2 = client.post(
            f"/api/v1/worker/process?job_id={job_id_2}",
            headers=auth_headers,
        )
        assert process2.status_code == 200
        assert process2.json()["state"] == "completed"
        # Should reuse the same extraction (idempotent).
        assert process2.json()["extraction_id"] == extraction_id_1


# === Test: Retry with backoff ===


class TestRetry:
    def test_retry_scheduled_on_failure(self, client, auth_headers, db_session, test_org, test_user):
        """When a job fails and attempts < max_attempts, it's scheduled for retry."""
        # Use a format that will fail (pdf_scanned -> OCR stub).
        doc, job = _create_document_with_job(
            db_session, test_org, test_user, b"\xff\xd8\xff\xe0 jpeg", "pdf_scanned"
        )

        claim = client.post("/api/v1/worker/claim", headers=auth_headers)
        assert claim.status_code == 200
        job_id = claim.json()["job_id"]

        process = client.post(
            f"/api/v1/worker/process?job_id={job_id}",
            headers=auth_headers,
        )
        assert process.status_code == 200
        body = process.json()
        assert body["state"] == "failed"

        # Verify the job is back to 'pending' with next_retry_at set.
        db_session.refresh(job)
        assert job.state == "pending"
        assert job.next_retry_at is not None
        assert job.attempts == 1

    def test_permanent_failure_after_max_attempts(self, client, auth_headers, db_session, test_org, test_user):
        """After max_attempts, the job stays in 'failed' permanently."""
        doc, job = _create_document_with_job(
            db_session, test_org, test_user, b"\xff\xd8\xff\xe0 jpeg", "pdf_scanned"
        )
        # Set max_attempts to 1 for this test.
        job.max_attempts = 1
        db_session.commit()

        claim = client.post("/api/v1/worker/claim", headers=auth_headers)
        assert claim.status_code == 200
        job_id = claim.json()["job_id"]

        process = client.post(
            f"/api/v1/worker/process?job_id={job_id}",
            headers=auth_headers,
        )
        assert process.status_code == 200
        body = process.json()
        assert body["state"] == "failed"

        # Verify the job is permanently failed.
        db_session.refresh(job)
        assert job.state == "failed"
        assert job.next_retry_at is None


# === Test: Lease reaping ===


class TestLeaseReaping:
    def test_reap_expired_leases(self, client, auth_headers, db_session, test_org, test_user):
        doc, job = _create_document_with_job(
            db_session, test_org, test_user, XML_INVOICE, "xml"
        )

        # Simulate a running job with expired lease.
        now = datetime.now(timezone.utc)
        job.state = "running"
        job.claimed_by = test_user.id
        job.claimed_at = now - timedelta(minutes=10)
        job.lease_expires_at = now - timedelta(minutes=5)  # Expired!
        db_session.commit()

        response = client.post("/api/v1/worker/reap", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["reaped_count"] == 1

        # Verify the job is back to pending.
        db_session.refresh(job)
        assert job.state == "pending"
        assert job.claimed_by is None

    def test_reap_no_expired(self, client, auth_headers, db_session, test_org, test_user):
        doc, job = _create_document_with_job(
            db_session, test_org, test_user, XML_INVOICE, "xml"
        )

        # Job is pending (not running), so nothing to reap.
        response = client.post("/api/v1/worker/reap", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["reaped_count"] == 0


# === Test: Document state update ===


class TestDocumentState:
    def test_document_state_updated_on_success(self, client, auth_headers, db_session, test_org, test_user):
        doc, job = _create_document_with_job(
            db_session, test_org, test_user, XML_INVOICE, "xml"
        )
        assert doc.state == "uploaded"

        claim = client.post("/api/v1/worker/claim", headers=auth_headers)
        job_id = claim.json()["job_id"]
        client.post(f"/api/v1/worker/process?job_id={job_id}", headers=auth_headers)

        db_session.refresh(doc)
        assert doc.state == "extracted"

    def test_document_state_updated_on_permanent_failure(self, client, auth_headers, db_session, test_org, test_user):
        doc, job = _create_document_with_job(
            db_session, test_org, test_user, b"\xff\xd8\xff\xe0 jpeg", "pdf_scanned"
        )
        job.max_attempts = 1
        db_session.commit()

        claim = client.post("/api/v1/worker/claim", headers=auth_headers)
        job_id = claim.json()["job_id"]
        client.post(f"/api/v1/worker/process?job_id={job_id}", headers=auth_headers)

        db_session.refresh(doc)
        assert doc.state == "failed"
        assert doc.failure_reason is not None
