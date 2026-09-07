"""Document split models (E19, INV-4).

A document split allows a single source document to feed multiple expenses.
The relationship between splits and expenses is modeled via the
``split_expenses`` intermediate table.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class DocumentSplit(Base):
    """A split of a source document into multiple expenses (E19)."""

    __tablename__ = "document_splits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_documents.id"),
        nullable=False,
        index=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentSplit id={self.id} document_id={self.document_id} "
            f"justification={self.justification!r}>"
        )


class SplitExpense(Base):
    """Intermediate table linking a split to an expense (E19)."""

    __tablename__ = "split_expenses"
    __table_args__ = (
        UniqueConstraint("split_id", "expense_id", name="uq_split_expenses"),
    )

    split_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_splits.id", ondelete="CASCADE"),
        primary_key=True,
    )
    expense_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("expenses.id", ondelete="CASCADE"),
        primary_key=True,
    )

    def __repr__(self) -> str:
        return (
            f"<SplitExpense split_id={self.split_id} "
            f"expense_id={self.expense_id}>"
        )
