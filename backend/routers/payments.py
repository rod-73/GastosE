"""Payments router (E12, VR-ARITH-5).

Endpoints:
- POST /api/v1/expenses/{expense_id}/payments: record a payment.
- GET /api/v1/expenses/{expense_id}/payments: list payments.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from backend.database import get_db
from backend.exceptions import ConflictException, ValidationException
from backend.middleware.auth import get_session, require_role
from backend.models.session import Session
from backend.services import payment_service

router = APIRouter(tags=["payments"])


class PaymentCreate(BaseModel):
    """Request schema for creating a payment."""

    payment_date: date
    amount_paid: Decimal
    payment_method_id: Optional[uuid.UUID] = None
    reference: Optional[str] = None


class PaymentResponse(BaseModel):
    """Response schema for a payment."""

    id: str
    expense_id: str
    payment_method_id: Optional[str] = None
    payment_date: str
    reference: Optional[str] = None
    amount_paid: str
    created_at: Optional[str] = None


@router.post(
    "/api/v1/expenses/{expense_id}/payments",
    response_model=PaymentResponse,
    status_code=201,
    dependencies=[Depends(require_role("reviewer"))],
)
def create_payment(
    expense_id: uuid.UUID,
    payload: PaymentCreate,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> PaymentResponse:
    """Record a payment for an expense."""
    try:
        payment = payment_service.record_payment(
            expense_id=expense_id,
            owner_id=session.organization_id,
            payment_date=payload.payment_date,
            amount_paid=payload.amount_paid,
            payment_method_id=payload.payment_method_id,
            reference=payload.reference,
            db=db,
        )
    except ValueError as e:
        if "VR-ARITH-5" in str(e):
            raise ValidationException(str(e))
        raise ConflictException(str(e))

    return PaymentResponse(
        id=str(payment.id),
        expense_id=str(payment.expense_id),
        payment_method_id=str(payment.payment_method_id) if payment.payment_method_id else None,
        payment_date=payment.payment_date.isoformat(),
        reference=payment.reference,
        amount_paid=str(payment.amount_paid),
        created_at=payment.created_at.isoformat() if payment.created_at else None,
    )


@router.get(
    "/api/v1/expenses/{expense_id}/payments",
    response_model=List[PaymentResponse],
    dependencies=[Depends(require_role("reader"))],
)
def list_payments(
    expense_id: uuid.UUID,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> List[PaymentResponse]:
    """List all payments for an expense."""
    payments = payment_service.get_payments(
        expense_id=expense_id,
        owner_id=session.organization_id,
        db=db,
    )
    return [PaymentResponse(**p) for p in payments]
