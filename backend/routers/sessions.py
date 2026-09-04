"""Session management endpoints (V8-S1).

- GET /api/v1/sessions: list active sessions for the current user.
- POST /api/v1/sessions/{session_id}/revoke: revoke a specific session.
- POST /api/v1/sessions/revoke-all: revoke all sessions for the current user.

ADR-0009: Opaque token + server-side session with revocation.
NFR-7: Authentication mandatory (except /healthz).
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from backend.database import get_db
from backend.exceptions import ConflictException, NotFoundException
from backend.middleware.auth import get_session, require_role
from backend.models.session import Session
from backend.services import session_service

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


# --- Schemas ---


class SessionSummaryResponse(BaseModel):
    """Summary of a session."""

    id: str
    role: str
    expires_at: str
    last_seen_at: str
    created_at: str
    is_current: bool


class SessionListResponse(BaseModel):
    """List of sessions."""

    count: int
    sessions: List[SessionSummaryResponse]


class RevokeResponse(BaseModel):
    """Response for revocation."""

    revoked: bool
    message: str


# --- Endpoints ---


@router.get(
    "",
    response_model=SessionListResponse,
    dependencies=[Depends(require_role("reader"))],
)
def list_sessions(
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> SessionListResponse:
    """List active sessions for the current user."""
    sessions = session_service.list_user_sessions(
        user_id=session.user_id,
        db=db,
    )
    current_token_hash = session.id
    return SessionListResponse(
        count=len(sessions),
        sessions=[
            SessionSummaryResponse(
                id=s.id[:8] + "...",  # Show only first 8 chars for security.
                role=s.role,
                expires_at=s.expires_at.isoformat(),
                last_seen_at=s.last_seen_at.isoformat(),
                created_at=s.created_at.isoformat(),
                is_current=(s.id == current_token_hash),
            )
            for s in sessions
        ],
    )


@router.post(
    "/{session_id}/revoke",
    response_model=RevokeResponse,
    dependencies=[Depends(require_role("reader"))],
)
def revoke_session(
    session_id: str,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> RevokeResponse:
    """Revoke a specific session.

    session_id is the full hash (sessions.id). Only the session owner
    or an admin can revoke.
    """
    try:
        revoked = session_service.revoke_session(
            session_id=session_id,
            user_id=session.user_id,
            role=session.role,
            db=db,
        )
    except ValueError as e:
        raise NotFoundException(str(e))

    if revoked:
        return RevokeResponse(revoked=True, message="Session revoked.")
    else:
        return RevokeResponse(revoked=False, message="Session already revoked or not found.")


@router.post(
    "/revoke-all",
    response_model=RevokeResponse,
    dependencies=[Depends(require_role("reader"))],
)
def revoke_all_sessions(
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> RevokeResponse:
    """Revoke all sessions for the current user."""
    count = session_service.revoke_all_user_sessions(
        user_id=session.user_id,
        db=db,
    )
    return RevokeResponse(
        revoked=True,
        message=f"Revoked {count} session(s).",
    )
