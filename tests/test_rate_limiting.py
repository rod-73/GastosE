"""Tests for rate limiting middleware (PHASE3-002)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.middleware.rate_limit import reset_rate_limiters


@pytest.fixture(autouse=True)
def _reset_limiters():
    """Reset rate limiters before each test."""
    reset_rate_limiters()
    yield
    reset_rate_limiters()


class TestLoginRateLimiting:
    """Login endpoint: 5 requests per minute per IP."""

    def test_login_allowed_under_limit(self, client: TestClient, auth_headers):
        """Login should succeed under the rate limit."""
        # auth_headers already performed one login.
        # Make 4 more (total 5).
        for _ in range(4):
            resp = client.post(
                "/api/v1/auth/login",
                json={"username": "testuser", "password": "testpass123"},
            )
            assert resp.status_code == 200

    def test_login_blocked_over_limit(self, client: TestClient):
        """Login should be blocked after 5 attempts per minute."""
        # Exhaust the limit with 5 failed attempts.
        for _ in range(5):
            client.post(
                "/api/v1/auth/login",
                json={"username": "testuser", "password": "wrongpass"},
            )
        # 6th attempt should be blocked.
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "testuser", "password": "testpass123"},
        )
        assert resp.status_code == 429
        assert resp.headers["content-type"] == "application/problem+json"
        body = resp.json()
        assert body["title"] == "Too many login attempts. Try again later."

    def test_login_rate_limit_per_ip(self, client: TestClient):
        """Rate limiting is per IP, not per user."""
        # Exhaust limit with one user.
        for _ in range(5):
            client.post(
                "/api/v1/auth/login",
                json={"username": "testuser", "password": "wrongpass"},
            )
        # Same IP, different user should also be blocked.
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "otheruser", "password": "wrongpass"},
        )
        assert resp.status_code == 429


class TestAPIRateLimiting:
    """API endpoints: 100 requests per minute per user."""

    def test_api_allowed_under_limit(self, client: TestClient, auth_headers):
        """API requests should succeed under the rate limit."""
        # Use a GET endpoint that exists. /api/v1/expenses/{id} requires a valid UUID.
        # Use a non-existent UUID to get 404 (but still counted for rate limiting).
        import uuid
        fake_id = str(uuid.uuid4())
        for _ in range(10):
            resp = client.get(f"/api/v1/expenses/{fake_id}", headers=auth_headers)
            # 404 is expected (non-existent expense), but rate limiting should not block.
            assert resp.status_code in (200, 404)

    def test_api_blocked_over_limit(self, client: TestClient, auth_headers):
        """API requests should be blocked after 100 per minute."""
        import uuid
        fake_id = str(uuid.uuid4())

        # Exhaust the limit (100 requests).
        for _ in range(100):
            client.get(f"/api/v1/expenses/{fake_id}", headers=auth_headers)

        # 101st request should be blocked.
        resp = client.get(f"/api/v1/expenses/{fake_id}", headers=auth_headers)
        assert resp.status_code == 429
        body = resp.json()
        assert body["title"] == "Too many requests. Try again later."
