"""Review endpoints (V4-S1, V4-S2, V4-S3, V4-S4).

- GET /api/v1/expenses/{id}/review: review view (five levels).
- POST /api/v1/expenses/{id}/review/decisions: apply review decision.
- POST /api/v1/expenses/{id}/accept: accept expense.
- POST /api/v1/expenses/{id}/reject: reject expense.
- POST /api/v1/expenses/{id}/void: void accepted expense.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from backend.database import get_db
from backend.exceptions import ConflictException, NotFoundException
from backend.middleware.auth import get_session, require_role
from backend.models.session import Session
from backend.services import review_service

router = APIRouter(tags=["review"])


# --- Schemas ---


class ReviewFieldResponse(BaseModel):
    """A single field in the review view."""

    field: str
    extracted: dict
    normalized: dict
    validated: dict
    accepted: Optional[dict]


class ReviewResponse(BaseModel):
    """Review view for an expense."""

    expense: dict
    fields: list
    document: dict


class ReviewDecisionRequest(BaseModel):
    """Request body for a review decision."""

    field: str
    decision: str  # confirm | correct | reject
    corrected_value: Optional[str] = None
    reason: Optional[str] = None


class ReviewDecisionResponse(BaseModel):
    """Response for a review decision."""

    field: str
    decision: str
    validated_value: str
    validation_result: str
    expense_state: str


class AcceptResponse(BaseModel):
    """Response for expense acceptance."""

    expense_id: uuid.UUID
    state: str
    accepted_at: str


class RejectRequest(BaseModel):
    """Request body for expense rejection."""

    reason: str


class RejectResponse(BaseModel):
    """Response for expense rejection."""

    expense_id: uuid.UUID
    state: str
    rejection_reason: str


class VoidRequest(BaseModel):
    """Request body for expense voiding."""

    reason: str


class VoidResponse(BaseModel):
    """Response for expense voiding."""

    expense_id: uuid.UUID
    state: str
    voided_at: str
    voided_reason: str


# --- Endpoints ---


@router.get(
    "/api/v1/expenses/{expense_id}/review",
    response_model=ReviewResponse,
    dependencies=[Depends(require_role("reader"))],
)
def get_review(
    expense_id: uuid.UUID,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> ReviewResponse:
    """Get the review view for an expense (V4-S1).

    Shows all five levels: extracted, normalized, validated, accepted,
    plus the source document for comparison.
    """
    try:
        data = review_service.get_review_view(
            expense_id=expense_id,
            owner_id=session.organization_id,
            db=db,
        )
    except ValueError as e:
        raise NotFoundException(str(e))

    return ReviewResponse(
        expense=data["expense"],
        fields=data["fields"],
        document=data["document"],
    )


@router.post(
    "/api/v1/expenses/{expense_id}/review/decisions",
    response_model=ReviewDecisionResponse,
    dependencies=[Depends(require_role("reviewer"))],
)
def apply_decision(
    expense_id: uuid.UUID,
    body: ReviewDecisionRequest,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> ReviewDecisionResponse:
    """Apply a review decision to a field (V4-S2).

    decision: confirm | correct | reject
    """
    try:
        result = review_service.apply_review_decision(
            expense_id=expense_id,
            owner_id=session.organization_id,
            user_id=session.user_id,
            field=body.field,
            decision=body.decision,
            corrected_value=body.corrected_value,
            reason=body.reason,
            db=db,
        )
    except ValueError as e:
        raise ConflictException(str(e))

    return ReviewDecisionResponse(**result)


@router.post(
    "/api/v1/expenses/{expense_id}/accept",
    response_model=AcceptResponse,
    dependencies=[Depends(require_role("approver"))],
)
def accept_expense(
    expense_id: uuid.UUID,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> AcceptResponse:
    """Accept an expense (V4-S3).

    Performs final validation and creates an immutable snapshot.
    """
    try:
        expense = review_service.accept_expense(
            expense_id=expense_id,
            owner_id=session.organization_id,
            user_id=session.user_id,
            db=db,
        )
    except ValueError as e:
        raise ConflictException(str(e))

    return AcceptResponse(
        expense_id=expense.id,
        state=expense.state,
        accepted_at=expense.accepted_at.isoformat() if expense.accepted_at else "",
    )


@router.post(
    "/api/v1/expenses/{expense_id}/reject",
    response_model=RejectResponse,
    dependencies=[Depends(require_role("reviewer"))],
)
def reject_expense(
    expense_id: uuid.UUID,
    body: RejectRequest,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> RejectResponse:
    """Reject an expense (V4-S4). Terminal action."""
    try:
        expense = review_service.reject_expense(
            expense_id=expense_id,
            owner_id=session.organization_id,
            user_id=session.user_id,
            reason=body.reason,
            db=db,
        )
    except ValueError as e:
        raise ConflictException(str(e))

    return RejectResponse(
        expense_id=expense.id,
        state=expense.state,
        rejection_reason=expense.rejection_reason or "",
    )


@router.post(
    "/api/v1/expenses/{expense_id}/void",
    response_model=VoidResponse,
    dependencies=[Depends(require_role("approver"))],
)
def void_expense(
    expense_id: uuid.UUID,
    body: VoidRequest,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> VoidResponse:
    """Void an accepted expense (V4-S4)."""
    try:
        expense = review_service.void_expense(
            expense_id=expense_id,
            owner_id=session.organization_id,
            user_id=session.user_id,
            reason=body.reason,
            db=db,
        )
    except ValueError as e:
        raise ConflictException(str(e))

    return VoidResponse(
        expense_id=expense.id,
        state=expense.state,
        voided_at=expense.voided_at.isoformat() if expense.voided_at else "",
        voided_reason=expense.voided_reason or "",
    )
