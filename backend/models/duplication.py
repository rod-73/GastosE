"""Duplication model (probable duplicates pending human resolution, DUP-1..6)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, func
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.utils import uuid7


class Duplication(Base):
    """A probable/confirmed duplicate pair of source documents."""

    __tablename__ = "duplications"
    __table_args__ = (
        CheckConstraint(
            "document_a_id != document_b_id",
            name="ck_duplications_documents_differ",
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
    document_a_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("source_documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    document_b_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("source_documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    dup_type: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="probable"
    )
    resolved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution_reason: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
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
            f"<Duplication id={self.id} a={self.document_a_id} "
            f"b={self.document_b_id} state={self.state}>"
        )
