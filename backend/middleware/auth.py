"""Authentication middleware and FastAPI dependencies (ADR-0009).

- ``auth_middleware``: validates the ``Authorization: Bearer <token>``
  header on every request (except the health endpoint) and stores the
  verified ``Session`` row in ``request.state.session``.
- ``get_session``: dependency that returns the session or raises 401.
- ``require_role``: dependency factory for role-based access control.
"""
from __future__ import annotations

import logging
from typing import Callable

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session as DbSession

from backend.database import get_db
from backend.exceptions import ForbiddenException, UnauthorizedException
from backend.models.session import Session
from backend.services.auth_service import verify_session

logger = logging.getLogger(__name__)

# Role hierarchy (NFR-7). Higher value => more privileges.
ROLE_ORDER: dict[str, int] = {
    "reader": 0,
    "reviewer": 1,
    "approver": 2,
    "admin": 3,
}

# Paths that do not require authentication.
PUBLIC_PATHS = {"/", "/healthz", "/api/v1/auth/login"}


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


async def auth_middleware(request: Request, call_next):
    """Verify the bearer token and attach the session to ``request.state``.

    Public paths (``/healthz``) skip authentication entirely. All other
    requests without a valid session receive a 401 problem+json response.
    """
    path = request.url.path
    if path in PUBLIC_PATHS:
        request.state.session = None
        return await call_next(request)

    authorization = request.headers.get("Authorization", "")
    if not authorization.lower().startswith("bearer "):
        return _problem(401, "auth.unauthorized", "Authentication required")

    token = authorization[7:].strip()
    if not token:
        return _problem(401, "auth.unauthorized", "Authentication required")

    # The middleware needs its own DB session (dependencies are per-route).
    # Use the app's configured session factory (allows test overrides).
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is not None:
        db = session_factory()
    else:
        from backend.database import get_session_local
        db = get_session_local()()
    try:
        session = verify_session(token, db)
    finally:
        db.close()

    if session is None:
        return _problem(401, "auth.unauthorized", "Authentication required")

    request.state.session = session
    return await call_next(request)


def get_session(request: Request) -> Session:
    """FastAPI dependency: return the verified session or raise 401."""
    session: Session | None = getattr(request.state, "session", None)
    if session is None:
        raise UnauthorizedException()
    return session


def require_role(min_role: str) -> Callable:
    """Dependency factory: require at least ``min_role`` privileges.

    Usage::

        @router.post("/", dependencies=[Depends(require_role("reader"))])
    """
    required_level = ROLE_ORDER.get(min_role)
    if required_level is None:
        raise ValueError(f"Unknown role: {min_role!r}")

    def _check(session: Session = Depends(get_session)) -> Session:
        current_level = ROLE_ORDER.get(session.role, -1)
        if current_level < required_level:
            raise ForbiddenException()
        return session

    return _check
