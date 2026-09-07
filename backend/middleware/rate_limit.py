"""Rate limiting middleware (docs/design/security/01-authentication.md).

- Login rate limiting: 5 requests per minute per IP.
- API rate limiting: 100 requests per minute per user (session).

Uses in-memory storage (V1). For production with multiple workers,
replace with Redis or database-backed counters.
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List

from fastapi import Request
from fastapi.responses import JSONResponse


@dataclass
class RateLimiter:
    """In-memory sliding window rate limiter."""

    window_seconds: float = 60.0
    max_requests: int = 5
    _requests: Dict[str, List[float]] = field(default_factory=lambda: defaultdict(list))

    def is_allowed(self, key: str) -> bool:
        """Check if a request is allowed for the given key."""
        now = time.time()
        # Remove requests outside the window.
        self._requests[key] = [
            t for t in self._requests[key] if now - t < self.window_seconds
        ]
        if len(self._requests[key]) >= self.max_requests:
            return False
        self._requests[key].append(now)
        return True

    def reset(self, key: str) -> None:
        """Reset the counter for a key."""
        self._requests.pop(key, None)

    def reset_all(self) -> None:
        """Reset all counters (for testing)."""
        self._requests.clear()


# Global rate limiters (module-level for simplicity in V1).
_login_limiter = RateLimiter(window_seconds=60.0, max_requests=5)
_api_limiter = RateLimiter(window_seconds=60.0, max_requests=100)


def _problem(status_code: int, code: str, message: str) -> JSONResponse:
    """Build an RFC 7807 problem+json response."""
    return JSONResponse(
        status_code=status_code,
        media_type="application/problem+json",
        content={
            "type": f"https://gastos.example/errors/{code}",
            "title": message,
            "status": status_code,
            "detail": message,
        },
    )


async def rate_limit_middleware(request: Request, call_next):
    """Apply rate limiting to incoming requests.

    - Login endpoint: limit by IP (5/min).
    - Other authenticated endpoints: limit by user/session (100/min).
    """
    path = request.url.path

    # Skip health endpoint.
    if path == "/healthz":
        return await call_next(request)

    # Login rate limiting (by IP).
    if path == "/api/v1/auth/login":
        client_ip = request.client.host if request.client else "unknown"
        if not _login_limiter.is_allowed(f"login:{client_ip}"):
            return _problem(
                429, "rate_limit.exceeded", "Too many login attempts. Try again later."
            )
        return await call_next(request)

    # API rate limiting (by user/session).
    # The session is set by auth_middleware (which runs before this middleware
    # in the stack order). If no session, skip rate limiting (unauthenticated
    # requests are handled by auth middleware).
    session = getattr(request.state, "session", None)
    if session is not None:
        user_key = f"api:{session.user_id}"
        if not _api_limiter.is_allowed(user_key):
            return _problem(
                429, "rate_limit.exceeded", "Too many requests. Try again later."
            )

    return await call_next(request)


def reset_rate_limiters() -> None:
    """Reset all rate limiters (for testing)."""
    _login_limiter.reset_all()
    _api_limiter.reset_all()
