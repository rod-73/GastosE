"""NormalizedValue model (E4).

Represents a normalized field value with reference to the original
extracted value (INV-10: no normalization without extraction origin).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.utils import uuid7


class NormalizedValue(Base):
    """A normalized field value (E4).

    INV-10: extracted_value_id is NOT NULL, guaranteeing that a value
    cannot be normalized without an extraction origin.
    """

    __tablename__ = "normalized_values"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), primary_key=True, default=uuid7
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    extracted_value_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("extracted_values.id", ondelete="RESTRICT"),
        nullable=False,
    )
    field: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value: Mapped[str] = mapped_column(Text, nullable=False)
    normalization_rule: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<NormalizedValue id={self.id} field={self.field} "
            f"rule={self.normalization_rule}>"
        )
