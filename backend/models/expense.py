"""Expense models (E6, E7, E8).

E6: Expense — the main expense record.
E7: ExpenseLine — individual line items.
E8: TaxLine — tax calculations per line or per expense.

INV-1: total == sum(bases) + sum(IVA) - sum(retenciones).
INV-3: document_id NOT NULL (expense references source document).
INV-13: Single currency.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.utils import uuid7


class Expense(Base):
    """An expense (E6).

    INV-3: document_id is NOT NULL.
    INV-13: Single currency (enforced by single currency field).
    """

    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("total >= 0", name="ck_expenses_total_nonneg"),
        CheckConstraint(
            "state IN ('draft', 'under_review', 'validation_error', 'duplicate', "
            "'ready_for_acceptance', 'accepted', 'voided', 'rejected', "
            "'confirmed_duplicate', 'failed')",
            name="ck_expenses_state",
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
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    document_number: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    document_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    currency: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    base_total: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    vat_total: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    withholding_total: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    total: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False
    )
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(), nullable=True
    )
    payment_method_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(), nullable=True
    )
    state: Mapped[str] = mapped_column(
        Text, nullable=False, default="draft"
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    accepted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(), nullable=True
    )
    accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accepted_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    voided_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(), nullable=True
    )
    voided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    voided_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<Expense id={self.id} total={self.total} "
            f"state={self.state}>"
        )


class ExpenseLine(Base):
    """An expense line item (E7)."""

    __tablename__ = "expense_lines"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_expense_lines_amount_nonneg"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), primary_key=True, default=uuid7
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    expense_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("expenses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 4), nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False
    )
    tax_rate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("tax_rates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<ExpenseLine id={self.id} amount={self.amount}>"
        )


class TaxLine(Base):
    """A tax line (E8).

    Can belong to an expense line or directly to an expense.
    """

    __tablename__ = "tax_lines"
    __table_args__ = (
        CheckConstraint("taxable_base >= 0", name="ck_tax_lines_base_nonneg"),
        CheckConstraint("tax_amount >= 0", name="ck_tax_lines_amount_nonneg"),
        CheckConstraint(
            "tax_type IN ('vat', 'withholding')",
            name="ck_tax_lines_type",
        ),
        CheckConstraint(
            "expense_line_id IS NOT NULL OR expense_id IS NOT NULL",
            name="ck_tax_lines_parent",
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
    expense_line_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(),
        ForeignKey("expense_lines.id", ondelete="RESTRICT"),
        nullable=True,
    )
    expense_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(),
        ForeignKey("expenses.id", ondelete="RESTRICT"),
        nullable=True,
    )
    tax_type: Mapped[str] = mapped_column(Text, nullable=False)
    tax_rate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("tax_rates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    taxable_base: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<TaxLine id={self.id} type={self.tax_type} "
            f"amount={self.tax_amount}>"
        )
