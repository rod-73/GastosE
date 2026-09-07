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
    # With synchronous extraction, the job is processed inline during upload.
    # The test PDF has no valid invoice fields, so extraction fails and the
    # job is scheduled for retry (state=pending, attempts=1).
    assert job.state in ("pending", "failed", "completed")
    assert job.attempts >= 1
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


# ─── V1-S2: verify-fingerprint ───────────────────────────────────────────────


def test_verify_fingerprint_matches(client: TestClient, auth_headers):
    """Verify fingerprint of a valid document returns matches=true."""
    upload_response = _upload(client, PDF_CONTENT, "test.pdf", auth_headers)
    assert upload_response.status_code == 202
    doc_id = upload_response.json()["id"]

    response = client.post(
        f"/api/v1/documents/{doc_id}/verify-fingerprint",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["matches"] is True
    assert data["fingerprint"] == hashlib.sha256(PDF_CONTENT).hexdigest()


def test_verify_fingerprint_not_found_returns_404(client: TestClient, auth_headers):
    """Verify fingerprint of a non-existent document returns 404."""
    fake_id = str(uuid.uuid4())
    response = client.post(
        f"/api/v1/documents/{fake_id}/verify-fingerprint",
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_verify_fingerprint_isolation_returns_404(client: TestClient, auth_headers, db_session):
    """User from org B cannot verify fingerprint of org A's document."""
    upload_response = _upload(client, PDF_CONTENT, "test.pdf", auth_headers)
    assert upload_response.status_code == 202
    doc_id = upload_response.json()["id"]

    import bcrypt
    from backend.models import Organization, User
    import uuid as uuid_mod

    org_b = Organization(id=uuid_mod.uuid4(), name="Org B", state="active")
    user_b = User(
        id=uuid_mod.uuid4(),
        organization_id=org_b.id,
        username="userb2",
        email="b2@example.com",
        password_hash=bcrypt.hashpw(b"pass123", bcrypt.gensalt()).decode("utf-8"),
        role="reader",
        state="active",
    )
    db_session.add(org_b)
    db_session.add(user_b)
    db_session.commit()

    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "userb2", "password": "pass123"},
    )
    assert login_response.status_code == 200
    token_b = login_response.json()["token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    response = client.post(
        f"/api/v1/documents/{doc_id}/verify-fingerprint",
        headers=headers_b,
    )
    assert response.status_code == 404


# ─── V1-S2: download content ─────────────────────────────────────────────────


def test_get_content_returns_file(client: TestClient, auth_headers):
    """Download document content returns the original bytes."""
    upload_response = _upload(client, PDF_CONTENT, "test.pdf", auth_headers)
    assert upload_response.status_code == 202
    doc_id = upload_response.json()["id"]

    response = client.get(f"/api/v1/documents/{doc_id}/content", headers=auth_headers)
    assert response.status_code == 200
    assert response.content == PDF_CONTENT
    assert "Content-Disposition" in response.headers
    assert "ETag" in response.headers


def test_get_content_not_found_returns_404(client: TestClient, auth_headers):
    """Download content of a non-existent document returns 404."""
    fake_id = str(uuid.uuid4())
    response = client.get(f"/api/v1/documents/{fake_id}/content", headers=auth_headers)
    assert response.status_code == 404


def test_get_content_isolation_returns_404(client: TestClient, auth_headers, db_session):
    """User from org B cannot download org A's document content."""
    upload_response = _upload(client, PDF_CONTENT, "test.pdf", auth_headers)
    assert upload_response.status_code == 202
    doc_id = upload_response.json()["id"]

    import bcrypt
    from backend.models import Organization, User
    import uuid as uuid_mod

    org_b = Organization(id=uuid_mod.uuid4(), name="Org B", state="active")
    user_b = User(
        id=uuid_mod.uuid4(),
        organization_id=org_b.id,
        username="userb3",
        email="b3@example.com",
        password_hash=bcrypt.hashpw(b"pass123", bcrypt.gensalt()).decode("utf-8"),
        role="reader",
        state="active",
    )
    db_session.add(org_b)
    db_session.add(user_b)
    db_session.commit()

    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "userb3", "password": "pass123"},
    )
    assert login_response.status_code == 200
    token_b = login_response.json()["token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    response = client.get(f"/api/v1/documents/{doc_id}/content", headers=headers_b)
    assert response.status_code == 404


# === Tests: DELETE /api/v1/documents/{id} ===


def test_delete_document_returns_200(client: TestClient, auth_headers, db_session):
    """Deleting an existing document returns 200 and removes it."""
    response = _upload(client, PDF_CONTENT, "test.pdf", auth_headers)
    assert response.status_code == 202
    doc_id = response.json()["id"]

    delete_resp = client.delete(f"/api/v1/documents/{doc_id}", headers=auth_headers)
    assert delete_resp.status_code == 200
    body = delete_resp.json()
    assert body["deleted"] is True
    assert body["id"] == doc_id

    # Document should be gone.
    get_resp = client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers)
    assert get_resp.status_code == 404


def test_delete_document_not_found_returns_404(client: TestClient, auth_headers):
    """Deleting a non-existent document returns 404."""
    fake_id = str(uuid.uuid4())
    response = client.delete(f"/api/v1/documents/{fake_id}", headers=auth_headers)
    assert response.status_code == 404


def test_delete_document_isolation_returns_404(client: TestClient, auth_headers, db_session):
    """User from org B cannot delete org A's document."""
    upload_response = _upload(client, PDF_CONTENT, "test.pdf", auth_headers)
    assert upload_response.status_code == 202
    doc_id = upload_response.json()["id"]

    import bcrypt
    from backend.models import Organization, User
    import uuid as uuid_mod

    org_b = Organization(id=uuid_mod.uuid4(), name="Org B Del", state="active")
    user_b = User(
        id=uuid_mod.uuid4(),
        organization_id=org_b.id,
        username="userb_del",
        email="b_del@example.com",
        password_hash=bcrypt.hashpw(b"pass123", bcrypt.gensalt()).decode("utf-8"),
        role="reader",
        state="active",
    )
    db_session.add(org_b)
    db_session.add(user_b)
    db_session.commit()

    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "userb_del", "password": "pass123"},
    )
    assert login_response.status_code == 200
    token_b = login_response.json()["token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    response = client.delete(f"/api/v1/documents/{doc_id}", headers=headers_b)
    assert response.status_code == 404

    # Original document still exists.
    get_resp = client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers)
    assert get_resp.status_code == 200


def test_delete_document_cascades_jobs(client: TestClient, auth_headers, db_session):
    """Deleting a document also removes its extraction jobs."""
    response = _upload(client, PDF_CONTENT, "test.pdf", auth_headers)
    assert response.status_code == 202
    doc_id = response.json()["id"]

    # Verify job exists.
    from backend.models import ExtractionJob
    job = db_session.query(ExtractionJob).filter_by(document_id=uuid.UUID(doc_id)).first()
    assert job is not None

    # Delete the document.
    delete_resp = client.delete(f"/api/v1/documents/{doc_id}", headers=auth_headers)
    assert delete_resp.status_code == 200

    # Job should be gone.
    job = db_session.query(ExtractionJob).filter_by(document_id=uuid.UUID(doc_id)).first()
    assert job is None


def test_delete_document_removes_file_from_storage(client: TestClient, auth_headers, db_session):
    """Deleting a document removes the file from storage."""
    import os
    from backend.config import get_settings

    response = _upload(client, PDF_CONTENT, "test.pdf", auth_headers)
    assert response.status_code == 202
    doc_id = response.json()["id"]
    fingerprint = response.json()["fingerprint_sha256"]

    # Verify file exists.
    settings = get_settings()
    from backend.models import Organization
    org = db_session.query(Organization).first()
    path = os.path.join(settings.DOCUMENT_STORAGE_PATH, str(org.id), fingerprint)
    assert os.path.isfile(path)

    # Delete.
    delete_resp = client.delete(f"/api/v1/documents/{doc_id}", headers=auth_headers)
    assert delete_resp.status_code == 200

    # File should be gone.
    assert not os.path.isfile(path)
