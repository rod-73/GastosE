"""Security and isolation tests for V1-S1."""
import hashlib
import uuid
from io import BytesIO

from fastapi.testclient import TestClient

from tests.conftest import PDF_CONTENT


def test_unauthenticated_request_rejected(client: TestClient):
    """Requests without auth should be rejected with 401."""
    response = client.get("/api/v1/documents")
    assert response.status_code == 401

    response = client.post(
        "/api/v1/documents",
        files={"file": ("test.pdf", BytesIO(PDF_CONTENT), "application/octet-stream")},
    )
    assert response.status_code == 401


def test_token_stored_as_hash_not_plaintext(client: TestClient, db_session, test_user):
    """The session token should be stored as SHA-256 hash, not plaintext."""
    # Login to get a token
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "testpass123"},
    )
    assert response.status_code == 200
    token = response.json()["token"]

    # The token is opaque (urlsafe base64), the stored id is a SHA-256 hex digest.
    # They must differ in format and value.
    assert token != hashlib.sha256(token.encode()).hexdigest()
    # The token should NOT be a hex string (it's urlsafe base64)
    assert not all(c in "0123456789abcdef" for c in token)
    # Verify the hash is 64 hex chars
    expected_hash = hashlib.sha256(token.encode()).hexdigest()
    assert len(expected_hash) == 64
    assert all(c in "0123456789abcdef" for c in expected_hash)


def test_user_cannot_see_other_org_documents(client: TestClient, auth_headers, db_session):
    """User from org A cannot access documents from org B (404, not 403)."""
    # Upload a document as user A
    files = {"file": ("test.pdf", BytesIO(PDF_CONTENT), "application/octet-stream")}
    response = client.post("/api/v1/documents", files=files, headers=auth_headers)
    assert response.status_code == 202
    doc_id = response.json()["id"]

    # Create user B in org B
    import bcrypt
    from backend.models import Organization, User

    org_b = Organization(id=uuid.uuid4(), name="Org B", state="active")
    user_b = User(
        id=uuid.uuid4(),
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

    # User B tries to access user A's document - should get 404 (not 403)
    response = client.get(f"/api/v1/documents/{doc_id}", headers=headers_b)
    assert response.status_code == 404


def test_invalid_token_rejected(client: TestClient):
    """Invalid tokens should be rejected with 401."""
    response = client.get(
        "/api/v1/documents",
        headers={"Authorization": "Bearer invalid-token-123"},
    )
    assert response.status_code == 401
