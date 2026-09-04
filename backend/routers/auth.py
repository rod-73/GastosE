"""Authentication endpoints (V8-S1): login / logout."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session as DbSession

from backend.database import get_db
from backend.middleware.auth import get_session
from backend.schemas.auth import LoginRequest, LoginResponse
from backend.services import auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    db: DbSession = Depends(get_db),
) -> LoginResponse:
    """Authenticate with username/password and return an opaque token."""
    token, expires_at = auth_service.login(payload.username, payload.password, db)
    return LoginResponse(token=token, expires_at=expires_at)


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    db: DbSession = Depends(get_db),
    _session=Depends(get_session),
) -> Response:
    """Revoke the current session. Idempotent (204 on repeat)."""
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token:
            auth_service.logout(token, db)
    return Response(status_code=204)
