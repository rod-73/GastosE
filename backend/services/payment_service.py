"""Payment service (E12, VR-ARITH-5).

Provides:
- record_payment: create a payment for an expense.
- get_payments: list payments for an expense.
- validate_payment: check VR-ARITH-5 (amount_paid == total with tolerance).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from backend.models.expense import Expense
from backend.models.payment import Payment
from backend.utils import uuid7


def record_payment(
    expense_id: uuid.UUID,
    owner_id: uuid.UUID,
    payment_date: date,
    amount_paid: Decimal,
    db: DbSession,
    payment_method_id: Optional[uuid.UUID] = None,
    reference: Optional[str] = None,
) -> Payment:
    """Record a payment for an expense.

    VR-ARITH-5: In single payment, amount_paid == total with tolerance <= 0.01.
    """
    # Get the expense to validate.
    expense = (
        db.execute(
            select(Expense).where(
                Expense.id == expense_id,
                Expense.owner_id == owner_id,
            )
        )
        .scalars()
        .first()
    )
    if expense is None:
        raise ValueError(f"Expense {expense_id} not found")

    # V1: Only single payment supported.
    existing_payments = (
        db.execute(
            select(Payment).where(
                Payment.expense_id == expense_id,
                Payment.owner_id == owner_id,
            )
        )
        .scalars()
        .all()
    )

    if len(existing_payments) > 0:
        raise ValueError(
            f"Expense {expense_id} already has a payment. "
            f"Multiple payments are not supported in V1."
        )

    # VR-ARITH-5: amount_paid must match total within tolerance.
    tolerance = Decimal("0.01")
    if abs(amount_paid - expense.total) > tolerance:
        raise ValueError(
            f"VR-ARITH-5 violation: amount_paid ({amount_paid}) != "
            f"total ({expense.total}) with tolerance {tolerance}"
        )

    payment = Payment(
        id=uuid7(),
        owner_id=owner_id,
        expense_id=expense_id,
        payment_method_id=payment_method_id,
        payment_date=payment_date,
        reference=reference,
        amount_paid=amount_paid,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


def get_payments(
    expense_id: uuid.UUID,
    owner_id: uuid.UUID,
    db: DbSession,
) -> List[Dict]:
    """List all payments for an expense."""
    payments = (
        db.execute(
            select(Payment)
            .where(
                Payment.expense_id == expense_id,
                Payment.owner_id == owner_id,
            )
            .order_by(Payment.payment_date)
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(p.id),
            "expense_id": str(p.expense_id),
            "payment_method_id": str(p.payment_method_id) if p.payment_method_id else None,
            "payment_date": p.payment_date.isoformat(),
            "reference": p.reference,
            "amount_paid": str(p.amount_paid),
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in payments
    ]
