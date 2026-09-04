"""Expense endpoints (V3-S3): creation from validated values.

- POST /api/v1/extractions/{id}/expenses: create an expense from validated values.
- GET /api/v1/expenses/{id}: get an expense with its lines.
- GET /api/v1/expenses: list expenses for the organization.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from backend.database import get_db
from backend.exceptions import ConflictException, NotFoundException
from backend.middleware.auth import get_session, require_role
from backend.models.document import SourceDocument
from backend.models.expense import Expense, ExpenseLine, TaxLine
from backend.models.extraction import Extraction
from backend.models.session import Session
from backend.services import expense_service
from backend.utils import uuid7

router = APIRouter(tags=["expenses"])


# --- Schemas ---


class ExpenseLineResponse(BaseModel):
    """A single expense line."""

    id: uuid.UUID
    description: str
    quantity: Optional[float]
    amount: float
    created_at: str


class TaxLineResponse(BaseModel):
    """A single tax line."""

    id: uuid.UUID
    tax_type: str
    taxable_base: float
    tax_amount: float
    created_at: str


class ExpenseResponse(BaseModel):
    """An expense with its lines."""

    id: uuid.UUID
    document_id: uuid.UUID
    supplier_id: uuid.UUID
    document_number: Optional[str]
    document_date: Optional[str]
    currency: str
    base_total: Optional[float]
    vat_total: Optional[float]
    withholding_total: Optional[float]
    total: float
    state: str
    created_at: str
    updated_at: str
    lines: List[ExpenseLineResponse]
    tax_lines: List[TaxLineResponse]


class CreateExpenseResponse(BaseModel):
    """Response for expense creation."""

    expense_id: uuid.UUID
    document_id: uuid.UUID
    total: float
    state: str


class ExpenseListResponse(BaseModel):
    """List of expenses."""

    count: int
    expenses: List[ExpenseResponse]


# --- Endpoints ---


@router.post(
    "/api/v1/extractions/{extraction_id}/expenses",
    response_model=CreateExpenseResponse,
    dependencies=[Depends(require_role("reader"))],
)
def create_expense(
    extraction_id: uuid.UUID,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> CreateExpenseResponse:
    """Create an expense (E6) from validated values (V3-S3).

    Precondition: validation must have been run and all BLOCK rules passed.
    Creates the expense, one expense line, and one tax line.
    """
    # Verify extraction exists and belongs to the caller.
    extraction = (
        db.execute(
            select(Extraction).where(
                Extraction.id == extraction_id,
                Extraction.owner_id == session.organization_id,
            )
        )
        .scalars()
        .first()
    )
    if extraction is None:
        raise NotFoundException("Extraction")

    # Check if an expense already exists for this document (idempotency).
    existing = (
        db.execute(
            select(Expense).where(
                Expense.document_id == extraction.document_id,
                Expense.owner_id == session.organization_id,
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return CreateExpenseResponse(
            expense_id=existing.id,
            document_id=existing.document_id,
            total=float(existing.total),
            state=existing.state,
        )

    # Create the expense.
    try:
        expense = expense_service.create_expense_from_validation(
            extraction_id=extraction_id,
            owner_id=session.organization_id,
            db=db,
        )
    except ValueError as e:
        raise ConflictException(str(e))

    return CreateExpenseResponse(
        expense_id=expense.id,
        document_id=expense.document_id,
        total=float(expense.total),
        state=expense.state,
    )


@router.get(
    "/api/v1/expenses/{expense_id}",
    response_model=ExpenseResponse,
    dependencies=[Depends(require_role("reader"))],
)
def get_expense(
    expense_id: uuid.UUID,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> ExpenseResponse:
    """Get an expense with its lines and tax lines."""
    expense = (
        db.execute(
            select(Expense).where(
                Expense.id == expense_id,
                Expense.owner_id == session.organization_id,
            )
        )
        .scalars()
        .first()
    )
    if expense is None:
        raise NotFoundException("Expense")

    lines = (
        db.execute(
            select(ExpenseLine)
            .where(ExpenseLine.expense_id == expense_id)
            .order_by(ExpenseLine.created_at.asc())
        )
        .scalars()
        .all()
    )

    tax_lines = (
        db.execute(
            select(TaxLine)
            .where(TaxLine.expense_id == expense_id)
            .order_by(TaxLine.created_at.asc())
        )
        .scalars()
        .all()
    )

    return ExpenseResponse(
        id=expense.id,
        document_id=expense.document_id,
        supplier_id=expense.supplier_id,
        document_number=expense.document_number,
        document_date=expense.document_date.isoformat() if expense.document_date else None,
        currency=expense.currency,
        base_total=float(expense.base_total) if expense.base_total is not None else None,
        vat_total=float(expense.vat_total) if expense.vat_total is not None else None,
        withholding_total=float(expense.withholding_total) if expense.withholding_total is not None else None,
        total=float(expense.total),
        state=expense.state,
        created_at=expense.created_at.isoformat() if expense.created_at else "",
        updated_at=expense.updated_at.isoformat() if expense.updated_at else "",
        lines=[
            ExpenseLineResponse(
                id=l.id,
                description=l.description,
                quantity=float(l.quantity) if l.quantity is not None else None,
                amount=float(l.amount),
                created_at=l.created_at.isoformat() if l.created_at else "",
            )
            for l in lines
        ],
        tax_lines=[
            TaxLineResponse(
                id=t.id,
                tax_type=t.tax_type,
                taxable_base=float(t.taxable_base),
                tax_amount=float(t.tax_amount),
                created_at=t.created_at.isoformat() if t.created_at else "",
            )
            for t in tax_lines
        ],
    )


@router.get(
    "/api/v1/expenses",
    response_model=ExpenseListResponse,
    dependencies=[Depends(require_role("reader"))],
)
def list_expenses(
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> ExpenseListResponse:
    """List all expenses for the organization."""
    expenses = (
        db.execute(
            select(Expense)
            .where(Expense.owner_id == session.organization_id)
            .order_by(Expense.created_at.desc())
        )
        .scalars()
        .all()
    )

    return ExpenseListResponse(
        count=len(expenses),
        expenses=[
            ExpenseResponse(
                id=e.id,
                document_id=e.document_id,
                supplier_id=e.supplier_id,
                document_number=e.document_number,
                document_date=e.document_date.isoformat() if e.document_date else None,
                currency=e.currency,
                base_total=float(e.base_total) if e.base_total is not None else None,
                vat_total=float(e.vat_total) if e.vat_total is not None else None,
                withholding_total=float(e.withholding_total) if e.withholding_total is not None else None,
                total=float(e.total),
                state=e.state,
                created_at=e.created_at.isoformat() if e.created_at else "",
                updated_at=e.updated_at.isoformat() if e.updated_at else "",
                lines=[],
                tax_lines=[],
            )
            for e in expenses
        ],
    )
