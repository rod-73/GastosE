"""Extraction and ExtractedValue models (E2, E3).

Implements the extraction result persistence layer:
- Extraction: one row per extraction attempt (method, state, timing).
- ExtractedValue: individual field values with confidence + provenance (INV-11).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.utils import uuid7


class Extraction(Base):
    """A single extraction attempt for a document (E2).

    State machine: pending -> running -> completed | failed | reprocessed.
    """

    __tablename__ = "extractions"
    __table_args__ = (
        CheckConstraint(
            "state != 'failed' OR failure_reason IS NOT NULL",
            name="ck_extractions_failed_requires_reason",
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
    method: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="pending"
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    values: Mapped[list["ExtractedValue"]] = relationship(
        "ExtractedValue", back_populates="extraction", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<Extraction id={self.id} document_id={self.document_id} "
            f"method={self.method} state={self.state}>"
        )


class ExtractedValue(Base):
    """A single extracted field value with confidence and provenance (E3).

    INV-11: confidence and provenance are NOT NULL.
    """

    __tablename__ = "extracted_values"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_extracted_values_confidence_range",
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
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("extractions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    field: Mapped[str] = mapped_column(Text, nullable=False)
    raw_value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(
        Numeric(4, 3), nullable=False
    )
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    extraction: Mapped["Extraction"] = relationship(
        "Extraction", back_populates="values"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<ExtractedValue id={self.id} field={self.field} "
            f"confidence={self.confidence}>"
        )
