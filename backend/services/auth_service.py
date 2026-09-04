"""Authentication service: login, logout, session verification (ADR-0009).

- Passwords are hashed with bcrypt via passlib (G12).
- Tokens are opaque: ``secrets.token_urlsafe(32)``.
- Only the SHA-256 hash of the token is stored (``sessions.id``).
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from backend.config import get_settings
from backend.models.session import Session
from backend.models.user import User


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Check a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def generate_token() -> str:
    """Generate an opaque session token."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Return the SHA-256 hex digest of a token (stored as sessions.id)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def login(
    username: str,
    password: str,
    db: DbSession,
) -> Tuple[str, datetime]:
    """Verify credentials and create a session.

    Returns ``(token, expires_at)``. Raises ``UnauthorizedException`` on
    bad credentials or inactive user.
    """
    from backend.exceptions import UnauthorizedException

    user = (
        db.execute(select(User).where(User.username == username))
        .scalars()
        .first()
    )
    if user is None or not verify_password(password, user.password_hash):
        raise UnauthorizedException()
    if user.state != "active":
        raise UnauthorizedException()

    settings = get_settings()
    token = generate_token()
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.SESSION_EXPIRY_DAYS
    )

    session = Session(
        id=hash_token(token),
        user_id=user.id,
        organization_id=user.organization_id,
        role=user.role,
        expires_at=expires_at,
    )
    db.add(session)
    db.commit()
    return token, expires_at


def logout(token: str, db: DbSession) -> None:
    """Revoke the session identified by ``token`` (idempotent)."""
    session = db.get(Session, hash_token(token))
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)
        db.commit()


def _ensure_aware(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware (SQLite returns naive datetimes)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def verify_session(token: str, db: DbSession) -> Optional[Session]:
    """Verify an opaque token: hash lookup, not revoked, not expired.

    Returns the ``Session`` row or ``None``.
    """
    if not token:
        return None
    session = db.get(Session, hash_token(token))
    if session is None:
        return None
    if session.revoked_at is not None:
        return None
    if _ensure_aware(session.expires_at) <= datetime.now(timezone.utc):
        return None
    return session
