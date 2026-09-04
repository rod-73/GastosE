"""Pydantic schemas for authentication endpoints (V8-S1)."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Credentials for ``POST /api/v1/auth/login``."""

    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=255)


class LoginResponse(BaseModel):
    """Opaque session token (ADR-0009) and its absolute expiry."""

    token: str
    expires_at: datetime


class SessionInfo(BaseModel):
    """Public view of the current session (user/org/role/expiry)."""

    user_id: UUID
    organization_id: UUID
    role: str
    expires_at: datetime
