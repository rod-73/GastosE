"""SourceDocument model (immutable primary evidence, ADR-0006)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
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


class SourceDocument(Base):
    """Original uploaded document. Content is immutable; identity is the
    SHA-256 fingerprint (INV-9, NFR-3)."""

    __tablename__ = "source_documents"
    __table_args__ = (
        CheckConstraint(
            "state != 'failed' OR failure_reason IS NOT NULL",
            name="ck_source_documents_failed_requires_reason",
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
    safe_name: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    fingerprint_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    doc_type: Mapped[str] = mapped_column(Text, nullable=False)
    format_detected: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    state: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="uploaded"
    )
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dup_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
            f"<SourceDocument id={self.id} "
            f"fingerprint={self.fingerprint_sha256[:8]}... state={self.state}>"
        )
