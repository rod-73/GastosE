"""Pydantic schemas for document endpoints (V1-S1)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentUploadResponse(BaseModel):
    """Response for ``POST /api/v1/documents`` (202 Accepted).

    Matches the ``Document`` contract fields relevant to the upload step.
    """

    id: UUID
    state: str
    fingerprint_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    safe_name: str
    uploaded_at: datetime


class DocumentResponse(BaseModel):
    """Full document view for ``GET /api/v1/documents/{id}``."""

    id: UUID
    owner_id: UUID
    safe_name: str
    original_filename: Optional[str] = None
    fingerprint_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    doc_type: str
    format_detected: str
    size_bytes: int
    page_count: Optional[int] = None
    uploaded_by: UUID
    uploaded_at: datetime
    state: str
    failure_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
