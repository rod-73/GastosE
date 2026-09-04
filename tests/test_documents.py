"""Tests for document upload and retrieval (V1-S1)."""
import hashlib
import uuid
from io import BytesIO

from fastapi.testclient import TestClient

from tests.conftest import (
    PDF_CONTENT,
    XML_CONTENT,
    JPEG_CONTENT,
    PNG_CONTENT,
    UNSUPPORTED_CONTENT,
    LARGE_PDF_CONTENT,
)


def _upload(client: TestClient, content: bytes, filename: str = "test.pdf", headers: dict = None) -> dict:
    """Helper to upload a document and return the response."""
    if headers is None:
        headers = {}
    files = {"file": (filename, BytesIO(content), "application/octet-stream")}
    response = client.post("/api/v1/documents", files=files, headers=headers)
    return response


def test_upload_pdf_returns_202(client: TestClient, auth_headers):
    response = _upload(client, PDF_CONTENT, "test.pdf", auth_headers)
    assert response.status_code == 202
    data = response.json()
    assert "id" in data
    assert data["state"] == "uploaded"
    assert "fingerprint_sha256" in data
    assert "safe_name" in data
    # Check Location header
    assert "location" in response.headers
    assert response.headers["location"].endswith(data["id"])


def test_upload_xml_returns_202(client: TestClient, auth_headers):
    response = _upload(client, XML_CONTENT, "invoice.xml", auth_headers)
    assert response.status_code == 202
    data = response.json()
    assert data["state"] == "uploaded"


def test_upload_jpeg_returns_202(client: TestClient, auth_headers):
    response = _upload(client, JPEG_CONTENT, "photo.jpg", auth_headers)
    assert response.status_code == 202


def test_upload_png_returns_202(client: TestClient, auth_headers):
    response = _upload(client, PNG_CONTENT, "image.png", auth_headers)
    assert response.status_code == 202


def test_upload_too_large_returns_413(client: TestClient, auth_headers):
    response = _upload(client, LARGE_PDF_CONTENT, "large.pdf", auth_headers)
    assert response.status_code == 413


def test_upload_unsupported_format_returns_415(client: TestClient, auth_headers):
    response = _upload(client, UNSUPPORTED_CONTENT, "notes.txt", auth_headers)
    assert response.status_code == 415


def test_upload_without_auth_returns_401(client: TestClient):
    response = _upload(client, PDF_CONTENT, "test.pdf")
    assert response.status_code == 401


def test_upload_creates_db_record(client: TestClient, auth_headers, db_session, test_org):
    response = _upload(client, PDF_CONTENT, "test.pdf", auth_headers)
    assert response.status_code == 202
    data = response.json()

    # Verify DB record
    from backend.models import SourceDocument
    doc = db_session.query(SourceDocument).filter_by(id=uuid.UUID(data["id"])).first()
    assert doc is not None
    assert doc.owner_id == test_org.id
    assert doc.fingerprint_sha256 == hashlib.sha256(PDF_CONTENT).hexdigest()
    assert doc.state == "uploaded"
    assert doc.format_detected == "pdf_text"
    assert doc.size_bytes == len(PDF_CONTENT)


def test_upload_creates_extraction_job(client: TestClient, auth_headers, db_session):
    response = _upload(client, PDF_CONTENT, "test.pdf", auth_headers)
    assert response.status_code == 202
    data = response.json()

    from backend.models import ExtractionJob
    job = db_session.query(ExtractionJob).filter_by(document_id=uuid.UUID(data["id"])).first()
    assert job is not None
    assert job.state == "pending"
    assert job.attempts == 0
    assert job.max_attempts == 3


def test_upload_creates_audit_event(client: TestClient, auth_headers, db_session, test_user):
    response = _upload(client, PDF_CONTENT, "test.pdf", auth_headers)
    assert response.status_code == 202
    data = response.json()

    from backend.models import AuditEvent
    event = (
        db_session.query(AuditEvent)
        .filter_by(entity_id=uuid.UUID(data["id"]))
        .first()
    )
    assert event is not None
    assert event.action == "document.uploaded"
    assert event.entity_type == "source_document"
    assert event.actor == test_user.id


def test_upload_duplicate_returns_409(client: TestClient, auth_headers):
    # Upload the same document twice
    response1 = _upload(client, PDF_CONTENT, "test1.pdf", auth_headers)
    assert response1.status_code == 202

    response2 = _upload(client, PDF_CONTENT, "test2.pdf", auth_headers)
    assert response2.status_code == 409
    data = response2.json()
    # RFC 7807 problem+json format
    assert data["status"] == 409
    assert data["type"] == "https://gastos.example/errors/conflict.duplicate"
    assert "already exists" in data["title"].lower()


def test_upload_idempotency_key_replay(client: TestClient, auth_headers):
    # Upload with Idempotency-Key
    headers = {**auth_headers, "Idempotency-Key": "test-key-123"}
    response1 = _upload(client, PDF_CONTENT, "test.pdf", headers)
    assert response1.status_code == 202

    # Replay with same key: returns the same response as the original (202)
    response2 = _upload(client, PDF_CONTENT, "test.pdf", headers)
    assert response2.status_code == 202  # Same status as original
    # Should return the same document ID
    assert response1.json()["id"] == response2.json()["id"]


def test_get_document_returns_200(client: TestClient, auth_headers):
    # Upload a document
    upload_response = _upload(client, PDF_CONTENT, "test.pdf", auth_headers)
    assert upload_response.status_code == 202
    doc_id = upload_response.json()["id"]

    # Get the document
    response = client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == doc_id
    assert data["state"] == "uploaded"
    assert data["fingerprint_sha256"] == hashlib.sha256(PDF_CONTENT).hexdigest()


def test_get_document_not_found_returns_404(client: TestClient, auth_headers):
    fake_id = str(uuid.uuid4())
    response = client.get(f"/api/v1/documents/{fake_id}", headers=auth_headers)
    assert response.status_code == 404


def test_get_document_isolation_returns_404(client: TestClient, auth_headers, db_session):
    """User from org A cannot see documents from org B."""
    # Upload a document as user A
    upload_response = _upload(client, PDF_CONTENT, "test.pdf", auth_headers)
    assert upload_response.status_code == 202
    doc_id = upload_response.json()["id"]

    # Create user B in a different org
    import bcrypt
    from backend.models import Organization, User
    import uuid as uuid_mod

    org_b = Organization(id=uuid_mod.uuid4(), name="Org B", state="active")
    user_b = User(
        id=uuid_mod.uuid4(),
        organization_id=org_b.id,
        username="userb",
        email="b@example.com",
        password_hash=bcrypt.hashpw(b"pass123", bcrypt.gensalt()).decode("utf-8"),
        role="reader",
        state="active",
    )
    db_session.add(org_b)
    db_session.add(user_b)
    db_session.commit()

    # Login as user B
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "userb", "password": "pass123"},
    )
    assert login_response.status_code == 200
    token_b = login_response.json()["token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Try to access user A's document
    response = client.get(f"/api/v1/documents/{doc_id}", headers=headers_b)
    assert response.status_code == 404
