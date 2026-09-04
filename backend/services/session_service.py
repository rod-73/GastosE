"""Session service (V8-S1).

Implements:
- list_user_sessions: list active sessions for a user.
- revoke_session: revoke a specific session.
- revoke_all_user_sessions: revoke all sessions for a user.

ADR-0009: Opaque token + server-side session with revocation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from backend.models.session import Session


def list_user_sessions(
    user_id,
    db: DbSession,
) -> List[Session]:
    """List active (non-revoked, non-expired) sessions for a user."""
    now = datetime.now(timezone.utc)
    sessions = (
        db.execute(
            select(Session)
            .where(
                Session.user_id == user_id,
                Session.revoked_at.is_(None),
                Session.expires_at > now,
            )
            .order_by(Session.created_at.desc())
        )
        .scalars()
        .all()
    )
    return list(sessions)


def revoke_session(
    session_id: str,
    user_id,
    role: str,
    db: DbSession,
) -> bool:
    """Revoke a specific session.

    Only the session owner or an admin can revoke.
    Returns True if the session was revoked, False if already revoked.
    Raises ValueError if the session doesn't exist or the user has no permission.
    """
    session = db.get(Session, session_id)
    if session is None:
        raise ValueError("Session not found")

    # Only the owner or an admin can revoke.
    if session.user_id != user_id and role != "admin":
        raise ValueError("Permission denied")

    if session.revoked_at is not None:
        return False

    session.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return True


def revoke_all_user_sessions(
    user_id,
    db: DbSession,
) -> int:
    """Revoke all active sessions for a user. Returns the count revoked."""
    now = datetime.now(timezone.utc)
    sessions = (
        db.execute(
            select(Session).where(
                Session.user_id == user_id,
                Session.revoked_at.is_(None),
                Session.expires_at > now,
            )
        )
        .scalars()
        .all()
    )

    count = 0
    for session in sessions:
        session.revoked_at = now
        count += 1

    db.commit()
    return count
