"""ValidatedValue model (E5).

Represents a validated field value with reference to the normalized value
(INV-10: no validation without normalization origin).

INV-8: A value cannot be validated without a normalized origin.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.utils import uuid7


class ValidatedValue(Base):
    """A validated field value (E5).

    INV-10: normalized_value_id is NOT NULL, guaranteeing that a value
    cannot be validated without a normalization origin.
    INV-8: Enforced by the FK to normalized_values.
    """

    __tablename__ = "validated_values"
    __table_args__ = (
        CheckConstraint(
            "validation_result IN ('passed', 'failed', 'warning', 'corrected')",
            name="ck_validated_values_result",
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
    normalized_value_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("normalized_values.id", ondelete="RESTRICT"),
        nullable=False,
    )
    field: Mapped[str] = mapped_column(Text, nullable=False)
    validated_value: Mapped[str] = mapped_column(Text, nullable=False)
    validation_result: Mapped[str] = mapped_column(Text, nullable=False)
    rules_applied: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<ValidatedValue id={self.id} field={self.field} "
            f"result={self.validation_result}>"
        )
