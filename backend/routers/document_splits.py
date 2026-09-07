"""Document splits router (E19, INV-4).

Endpoints:
- POST /api/v1/documents/{document_id}/splits: create a split.
- POST /api/v1/splits/{split_id}/expenses: link an expense to a split.
- GET /api/v1/splits/{split_id}: get a split with its expenses.
- GET /api/v1/documents/{document_id}/splits: list splits for a document.
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from backend.database import get_db
from backend.exceptions import ConflictException, NotFoundException, ValidationException
from backend.middleware.auth import get_session, require_role
from backend.models.session import Session
from backend.services import document_split_service

router = APIRouter(tags=["document-splits"])


class SplitCreate(BaseModel):
    """Request schema for creating a split."""

    justification: str


class SplitExpenseLink(BaseModel):
    """Request schema for linking an expense to a split."""

    expense_id: uuid.UUID


class SplitResponse(BaseModel):
    """Response schema for a split."""

    id: str
    document_id: str
    created_by: str
    justification: str
    created_at: Optional[str] = None
    expenses: List[dict] = []


@router.post(
    "/api/v1/documents/{document_id}/splits",
    response_model=SplitResponse,
    status_code=201,
    dependencies=[Depends(require_role("reviewer"))],
)
def create_split(
    document_id: uuid.UUID,
    payload: SplitCreate,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> SplitResponse:
    """Create a document split."""
    try:
        split = document_split_service.create_split(
            document_id=document_id,
            owner_id=session.organization_id,
            created_by=session.user_id,
            justification=payload.justification,
            db=db,
        )
    except ValueError as e:
        if "not found" in str(e):
            raise NotFoundException("Document")
        raise ConflictException(str(e))

    split_data = document_split_service.get_split(split.id, session.organization_id, db)
    return SplitResponse(**split_data)


@router.post(
    "/api/v1/splits/{split_id}/expenses",
    status_code=201,
    dependencies=[Depends(require_role("reviewer"))],
)
def add_expense_to_split(
    split_id: uuid.UUID,
    payload: SplitExpenseLink,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> dict:
    """Link an expense to a split."""
    try:
        link = document_split_service.add_expense_to_split(
            split_id=split_id,
            expense_id=payload.expense_id,
            owner_id=session.organization_id,
            db=db,
        )
    except ValueError as e:
        if "not found" in str(e):
            raise NotFoundException("Resource")
        raise ConflictException(str(e))

    return {"split_id": str(link.split_id), "expense_id": str(link.expense_id)}


@router.get(
    "/api/v1/splits/{split_id}",
    response_model=SplitResponse,
    dependencies=[Depends(require_role("reader"))],
)
def get_split(
    split_id: uuid.UUID,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> SplitResponse:
    """Get a split with its expenses."""
    split_data = document_split_service.get_split(
        split_id=split_id,
        owner_id=session.organization_id,
        db=db,
    )
    if split_data is None:
        raise NotFoundException("Split")
    return SplitResponse(**split_data)


@router.get(
    "/api/v1/documents/{document_id}/splits",
    response_model=List[SplitResponse],
    dependencies=[Depends(require_role("reader"))],
)
def list_splits(
    document_id: uuid.UUID,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> List[SplitResponse]:
    """List splits for a document."""
    splits = document_split_service.list_splits(
        document_id=document_id,
        owner_id=session.organization_id,
        db=db,
    )
    return [SplitResponse(**s) for s in splits]
