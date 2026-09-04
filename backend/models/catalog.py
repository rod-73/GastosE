"""Catalog models: Supplier, TaxRate, Currency, Category, PaymentMethod.

These tables are created by migration 0001 (foundation) but were not
previously registered as ORM models. They are needed for:
- Expense creation (V3-S3): supplier_id, tax_rate_id FKs.
- Supplier CRUD (V6-S1).
- Catalog CRUD (V6-S2).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.utils import uuid7


class Supplier(Base):
    """A supplier (V6-S1)."""

    __tablename__ = "suppliers"
    __table_args__ = (
        CheckConstraint(
            "state IN ('active', 'inactive')", name="chk_sup_state"
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
    legal_name: Mapped[str] = mapped_column(Text, nullable=False)
    nif_cif: Mapped[str] = mapped_column(Text, nullable=False)
    tax_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contact_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(
        Text, nullable=False, default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Supplier id={self.id} name={self.legal_name!r}>"


class TaxRate(Base):
    """A tax rate (V6-S2)."""

    __tablename__ = "tax_rates"
    __table_args__ = (
        CheckConstraint(
            "tax_type IN ('vat', 'withholding')", name="chk_tax_rate_type"
        ),
        CheckConstraint(
            "percentage >= 0 AND percentage <= 100", name="chk_tax_rate_pct"
        ),
        CheckConstraint(
            "valid_until IS NULL OR valid_until >= valid_from",
            name="chk_tax_rate_validity",
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
    code: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tax_type: Mapped[str] = mapped_column(Text, nullable=False)
    percentage: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False
    )
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    jurisdiction: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<TaxRate id={self.id} code={self.code!r} pct={self.percentage}>"


class Currency(Base):
    """A currency code (global catalog, V6-S2)."""

    __tablename__ = "currencies"
    __table_args__ = (
        CheckConstraint(
            "decimals >= 0 AND decimals <= 4", name="chk_currency_decimals"
        ),
    )

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    decimals: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Currency code={self.code!r}>"


class Category(Base):
    """An expense category (V6-S2)."""

    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint(
            "state IN ('active', 'inactive')", name="chk_cat_state"
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
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    state: Mapped[str] = mapped_column(
        Text, nullable=False, default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Category id={self.id} name={self.name!r}>"


class PaymentMethod(Base):
    """A payment method (V6-S2)."""

    __tablename__ = "payment_methods"
    __table_args__ = (
        CheckConstraint(
            "state IN ('active', 'inactive')", name="chk_pm_state"
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
    name: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(
        Text, nullable=False, default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<PaymentMethod id={self.id} name={self.name!r}>"
