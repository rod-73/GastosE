"""Tests for the /healthz endpoint."""
from fastapi.testclient import TestClient


def test_healthz_returns_200(client: TestClient):
    response = client.get("/healthz")
    assert response.status_code == 200


def test_healthz_no_auth_required(client: TestClient):
    """Health endpoint should not require authentication."""
    response = client.get("/healthz")
    assert response.status_code == 200
    # Should not return 401
