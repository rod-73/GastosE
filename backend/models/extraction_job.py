"""ExtractionJob model (database-backed work queue, ADR-0005)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    func,
)
from sqlalchemy import CHAR, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.utils import uuid7


class ExtractionJob(Base):
    """Unit of work for the extraction worker (claim/lease/retry semantics)."""

    __tablename__ = "extraction_jobs"
    __table_args__ = (
        CheckConstraint(
            "state != 'failed' OR failure_reason IS NOT NULL",
            name="ck_extraction_jobs_failed_requires_reason",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), primary_key=True, default=uuid7
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("source_documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    document_fingerprint: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    format_detected: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="pending"
    )
    claimed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(), nullable=True
    )
    claimed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="3"
    )
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    failure_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extraction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<ExtractionJob id={self.id} document_id={self.document_id} "
            f"state={self.state}>"
        )
