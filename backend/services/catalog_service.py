"""Catalog service (V6-S2).

Implements CRUD for:
- Categories: create, list, get, update, deactivate.
- PaymentMethods: create, list, get, update, deactivate.
- TaxRates: create, list, get, update, deactivate.
- Currencies: list, get (global catalog, read-only).

FR-CAT-1: Define expense categories.
FR-CAT-2: Accepted expenses must have a category (if policy requires).
FR-CAT-3: List expenses by category.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session as DbSession

from backend.models.audit_event import AuditEvent
from backend.models.catalog import Category, Currency, PaymentMethod, TaxRate
from backend.utils import uuid7


# --- Categories ---


def create_category(
    owner_id: uuid.UUID,
    user_id: uuid.UUID,
    name: str,
    description: Optional[str] = None,
    parent_id: Optional[uuid.UUID] = None,
    db: Optional[DbSession] = None,
) -> Category:
    """Create a new category (FR-CAT-1)."""
    if not name or not name.strip():
        raise ValueError("Category name is required.")

    category = Category(
        id=uuid7(),
        owner_id=owner_id,
        name=name.strip(),
        description=description,
        parent_id=parent_id,
        state="active",
    )
    db.add(category)
    db.flush()

    audit = AuditEvent(
        id=uuid7(),
        owner_id=owner_id,
        entity_type="category",
        entity_id=category.id,
        action="category.created",
        actor=user_id,
        after_data={
            "name": category.name,
            "description": category.description,
            "state": category.state,
        },
    )
    db.add(audit)

    db.commit()
    db.refresh(category)
    return category


def get_category(
    category_id: uuid.UUID,
    owner_id: uuid.UUID,
    db: DbSession,
) -> Category:
    """Get a single category. Raises ValueError if not found."""
    category = (
        db.execute(
            select(Category).where(
                Category.id == category_id,
                Category.owner_id == owner_id,
            )
        )
        .scalars()
        .first()
    )
    if category is None:
        raise ValueError("Category not found")
    return category


def list_categories(
    owner_id: uuid.UUID,
    db: DbSession,
    state: Optional[str] = None,
) -> List[Category]:
    """List categories with optional state filter."""
    query = select(Category).where(Category.owner_id == owner_id)

    if state is not None:
        query = query.where(Category.state == state)

    categories = (
        db.execute(query.order_by(Category.name.asc()))
        .scalars()
        .all()
    )
    return list(categories)


def update_category(
    category_id: uuid.UUID,
    owner_id: uuid.UUID,
    user_id: uuid.UUID,
    name: Optional[str] = None,
    description: Optional[str] = None,
    parent_id: Optional[uuid.UUID] = None,
    db: Optional[DbSession] = None,
) -> Category:
    """Update a category."""
    category = get_category(category_id, owner_id, db)

    before = {
        "name": category.name,
        "description": category.description,
    }

    if name is not None and name.strip():
        category.name = name.strip()

    if description is not None:
        category.description = description

    if parent_id is not None:
        category.parent_id = parent_id

    category.updated_at = datetime.now(timezone.utc)

    audit = AuditEvent(
        id=uuid7(),
        owner_id=owner_id,
        entity_type="category",
        entity_id=category.id,
        action="category.updated",
        actor=user_id,
        before_data=before,
        after_data={
            "name": category.name,
            "description": category.description,
        },
    )
    db.add(audit)

    db.commit()
    db.refresh(category)
    return category


def deactivate_category(
    category_id: uuid.UUID,
    owner_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: Optional[str] = None,
    db: Optional[DbSession] = None,
) -> Category:
    """Deactivate a category."""
    category = get_category(category_id, owner_id, db)

    if category.state == "inactive":
        raise ValueError("Category is already inactive.")

    before = {"state": category.state}
    category.state = "inactive"
    category.updated_at = datetime.now(timezone.utc)

    audit = AuditEvent(
        id=uuid7(),
        owner_id=owner_id,
        entity_type="category",
        entity_id=category.id,
        action="category.deactivated",
        actor=user_id,
        before_data=before,
        after_data={"state": "inactive", "reason": reason},
    )
    db.add(audit)

    db.commit()
    db.refresh(category)
    return category


# --- Payment Methods ---


def create_payment_method(
    owner_id: uuid.UUID,
    user_id: uuid.UUID,
    name: str,
    db: Optional[DbSession] = None,
) -> PaymentMethod:
    """Create a new payment method."""
    if not name or not name.strip():
        raise ValueError("Payment method name is required.")

    pm = PaymentMethod(
        id=uuid7(),
        owner_id=owner_id,
        name=name.strip(),
        state="active",
    )
    db.add(pm)
    db.flush()

    audit = AuditEvent(
        id=uuid7(),
        owner_id=owner_id,
        entity_type="payment_method",
        entity_id=pm.id,
        action="payment_method.created",
        actor=user_id,
        after_data={
            "name": pm.name,
            "state": pm.state,
        },
    )
    db.add(audit)

    db.commit()
    db.refresh(pm)
    return pm


def get_payment_method(
    pm_id: uuid.UUID,
    owner_id: uuid.UUID,
    db: DbSession,
) -> PaymentMethod:
    """Get a single payment method. Raises ValueError if not found."""
    pm = (
        db.execute(
            select(PaymentMethod).where(
                PaymentMethod.id == pm_id,
                PaymentMethod.owner_id == owner_id,
            )
        )
        .scalars()
        .first()
    )
    if pm is None:
        raise ValueError("Payment method not found")
    return pm


def list_payment_methods(
    owner_id: uuid.UUID,
    db: DbSession,
    state: Optional[str] = None,
) -> List[PaymentMethod]:
    """List payment methods with optional state filter."""
    query = select(PaymentMethod).where(PaymentMethod.owner_id == owner_id)

    if state is not None:
        query = query.where(PaymentMethod.state == state)

    pms = (
        db.execute(query.order_by(PaymentMethod.name.asc()))
        .scalars()
        .all()
    )
    return list(pms)


def update_payment_method(
    pm_id: uuid.UUID,
    owner_id: uuid.UUID,
    user_id: uuid.UUID,
    name: Optional[str] = None,
    db: Optional[DbSession] = None,
) -> PaymentMethod:
    """Update a payment method."""
    pm = get_payment_method(pm_id, owner_id, db)

    before = {"name": pm.name}

    if name is not None and name.strip():
        pm.name = name.strip()

    pm.updated_at = datetime.now(timezone.utc)

    audit = AuditEvent(
        id=uuid7(),
        owner_id=owner_id,
        entity_type="payment_method",
        entity_id=pm.id,
        action="payment_method.updated",
        actor=user_id,
        before_data=before,
        after_data={"name": pm.name},
    )
    db.add(audit)

    db.commit()
    db.refresh(pm)
    return pm


def deactivate_payment_method(
    pm_id: uuid.UUID,
    owner_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: Optional[str] = None,
    db: Optional[DbSession] = None,
) -> PaymentMethod:
    """Deactivate a payment method."""
    pm = get_payment_method(pm_id, owner_id, db)

    if pm.state == "inactive":
        raise ValueError("Payment method is already inactive.")

    before = {"state": pm.state}
    pm.state = "inactive"
    pm.updated_at = datetime.now(timezone.utc)

    audit = AuditEvent(
        id=uuid7(),
        owner_id=owner_id,
        entity_type="payment_method",
        entity_id=pm.id,
        action="payment_method.deactivated",
        actor=user_id,
        before_data=before,
        after_data={"state": "inactive", "reason": reason},
    )
    db.add(audit)

    db.commit()
    db.refresh(pm)
    return pm


# --- Tax Rates ---


def create_tax_rate(
    owner_id: uuid.UUID,
    user_id: uuid.UUID,
    code: str,
    tax_type: str,
    percentage: Decimal,
    valid_from: date,
    description: Optional[str] = None,
    valid_until: Optional[date] = None,
    jurisdiction: Optional[str] = None,
    db: Optional[DbSession] = None,
) -> TaxRate:
    """Create a new tax rate."""
    if not code or not code.strip():
        raise ValueError("Tax rate code is required.")

    if tax_type not in ("vat", "withholding"):
        raise ValueError("Tax type must be 'vat' or 'withholding'.")

    if percentage < 0 or percentage > 100:
        raise ValueError("Percentage must be between 0 and 100.")

    if valid_until is not None and valid_until < valid_from:
        raise ValueError("valid_until must be >= valid_from.")

    tax_rate = TaxRate(
        id=uuid7(),
        owner_id=owner_id,
        code=code.strip(),
        description=description,
        tax_type=tax_type,
        percentage=percentage,
        valid_from=valid_from,
        valid_until=valid_until,
        jurisdiction=jurisdiction,
    )
    db.add(tax_rate)
    db.flush()

    audit = AuditEvent(
        id=uuid7(),
        owner_id=owner_id,
        entity_type="tax_rate",
        entity_id=tax_rate.id,
        action="tax_rate.created",
        actor=user_id,
        after_data={
            "code": tax_rate.code,
            "tax_type": tax_rate.tax_type,
            "percentage": str(tax_rate.percentage),
            "valid_from": tax_rate.valid_from.isoformat(),
        },
    )
    db.add(audit)

    db.commit()
    db.refresh(tax_rate)
    return tax_rate


def get_tax_rate(
    tax_rate_id: uuid.UUID,
    owner_id: uuid.UUID,
    db: DbSession,
) -> TaxRate:
    """Get a single tax rate. Raises ValueError if not found."""
    tax_rate = (
        db.execute(
            select(TaxRate).where(
                TaxRate.id == tax_rate_id,
                TaxRate.owner_id == owner_id,
            )
        )
        .scalars()
        .first()
    )
    if tax_rate is None:
        raise ValueError("Tax rate not found")
    return tax_rate


def list_tax_rates(
    owner_id: uuid.UUID,
    db: DbSession,
    tax_type: Optional[str] = None,
    state: Optional[str] = None,
) -> List[TaxRate]:
    """List tax rates with optional filters."""
    query = select(TaxRate).where(TaxRate.owner_id == owner_id)

    if tax_type is not None:
        query = query.where(TaxRate.tax_type == tax_type)

    tax_rates = (
        db.execute(query.order_by(TaxRate.code.asc()))
        .scalars()
        .all()
    )
    return list(tax_rates)


def update_tax_rate(
    tax_rate_id: uuid.UUID,
    owner_id: uuid.UUID,
    user_id: uuid.UUID,
    code: Optional[str] = None,
    description: Optional[str] = None,
    percentage: Optional[Decimal] = None,
    valid_until: Optional[date] = None,
    db: Optional[DbSession] = None,
) -> TaxRate:
    """Update a tax rate."""
    tax_rate = get_tax_rate(tax_rate_id, owner_id, db)

    before = {
        "code": tax_rate.code,
        "percentage": str(tax_rate.percentage),
        "valid_until": tax_rate.valid_until.isoformat() if tax_rate.valid_until else None,
    }

    if code is not None and code.strip():
        tax_rate.code = code.strip()

    if description is not None:
        tax_rate.description = description

    if percentage is not None:
        if percentage < 0 or percentage > 100:
            raise ValueError("Percentage must be between 0 and 100.")
        tax_rate.percentage = percentage

    if valid_until is not None:
        if valid_until < tax_rate.valid_from:
            raise ValueError("valid_until must be >= valid_from.")
        tax_rate.valid_until = valid_until

    tax_rate.updated_at = datetime.now(timezone.utc)

    audit = AuditEvent(
        id=uuid7(),
        owner_id=owner_id,
        entity_type="tax_rate",
        entity_id=tax_rate.id,
        action="tax_rate.updated",
        actor=user_id,
        before_data=before,
        after_data={
            "code": tax_rate.code,
            "percentage": str(tax_rate.percentage),
            "valid_until": tax_rate.valid_until.isoformat() if tax_rate.valid_until else None,
        },
    )
    db.add(audit)

    db.commit()
    db.refresh(tax_rate)
    return tax_rate


def deactivate_tax_rate(
    tax_rate_id: uuid.UUID,
    owner_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: Optional[str] = None,
    db: Optional[DbSession] = None,
) -> TaxRate:
    """Deactivate a tax rate by setting valid_until to today."""
    tax_rate = get_tax_rate(tax_rate_id, owner_id, db)

    if tax_rate.valid_until is not None and tax_rate.valid_until <= date.today():
        raise ValueError("Tax rate is already expired.")

    before = {
        "valid_until": tax_rate.valid_until.isoformat() if tax_rate.valid_until else None,
    }
    tax_rate.valid_until = date.today()
    tax_rate.updated_at = datetime.now(timezone.utc)

    audit = AuditEvent(
        id=uuid7(),
        owner_id=owner_id,
        entity_type="tax_rate",
        entity_id=tax_rate.id,
        action="tax_rate.deactivated",
        actor=user_id,
        before_data=before,
        after_data={
            "valid_until": tax_rate.valid_until.isoformat(),
            "reason": reason,
        },
    )
    db.add(audit)

    db.commit()
    db.refresh(tax_rate)
    return tax_rate


# --- Currencies (global catalog, read-only) ---


def list_currencies(
    db: DbSession,
) -> List[Currency]:
    """List all currencies (global catalog)."""
    currencies = (
        db.execute(select(Currency).order_by(Currency.code.asc()))
        .scalars()
        .all()
    )
    return list(currencies)


def get_currency(
    code: str,
    db: DbSession,
) -> Currency:
    """Get a single currency by code. Raises ValueError if not found."""
    currency = (
        db.execute(select(Currency).where(Currency.code == code))
        .scalars()
        .first()
    )
    if currency is None:
        raise ValueError(f"Currency '{code}' not found")
    return currency
