"""Duplication endpoints (V5-S1, V5-S2).

- GET /api/v1/duplications: list duplications for the organization.
- GET /api/v1/duplications/{id}: get a single duplication with details.
- POST /api/v1/duplications/{id}/resolve: resolve a probable duplication.
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from backend.database import get_db
from backend.exceptions import ConflictException, NotFoundException
from backend.middleware.auth import get_session, require_role
from backend.models.session import Session
from backend.services import duplication_service

router = APIRouter(tags=["duplications"])


# --- Schemas ---


class DuplicationSummaryResponse(BaseModel):
    """Summary of a duplication (for list view)."""

    id: uuid.UUID
    document_a_id: uuid.UUID
    document_b_id: uuid.UUID
    document_a_fingerprint: Optional[str]
    document_b_fingerprint: Optional[str]
    document_a_state: Optional[str]
    document_b_state: Optional[str]
    dup_type: str
    state: str
    resolved_by: Optional[str]
    resolved_at: Optional[str]
    resolution_reason: Optional[str]
    created_at: str


class DuplicationListResponse(BaseModel):
    """List of duplications."""

    count: int
    duplications: List[DuplicationSummaryResponse]


class DuplicationDetailResponse(BaseModel):
    """Detailed duplication with document info."""

    id: uuid.UUID
    document_a_id: uuid.UUID
    document_b_id: uuid.UUID
    document_a: dict
    document_b: dict
    dup_type: str
    state: str
    resolved_by: Optional[str]
    resolved_at: Optional[str]
    resolution_reason: Optional[str]
    created_at: str


class ResolveDuplicationRequest(BaseModel):
    """Request body for resolving a duplication."""

    resolution: str  # confirmed | not_duplicate
    reason: str


class ResolveDuplicationResponse(BaseModel):
    """Response for duplication resolution."""

    id: uuid.UUID
    state: str
    resolved_by: str
    resolved_at: str
    resolution_reason: str


# --- Endpoints ---


@router.get(
    "/api/v1/duplications",
    response_model=DuplicationListResponse,
    dependencies=[Depends(require_role("reader"))],
)
def list_duplications(
    state: Optional[str] = None,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> DuplicationListResponse:
    """List duplications for the organization.

    Optionally filter by state (probable, confirmed, not_duplicate).
    """
    dups = duplication_service.list_duplications(
        owner_id=session.organization_id,
        db=db,
        state=state,
    )
    return DuplicationListResponse(
        count=len(dups),
        duplications=[DuplicationSummaryResponse(**d) for d in dups],
    )


@router.get(
    "/api/v1/duplications/{duplication_id}",
    response_model=DuplicationDetailResponse,
    dependencies=[Depends(require_role("reader"))],
)
def get_duplication(
    duplication_id: uuid.UUID,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> DuplicationDetailResponse:
    """Get a single duplication with document details."""
    try:
        data = duplication_service.get_duplication(
            duplication_id=duplication_id,
            owner_id=session.organization_id,
            db=db,
        )
    except ValueError as e:
        raise NotFoundException(str(e))

    return DuplicationDetailResponse(**data)


@router.post(
    "/api/v1/duplications/{duplication_id}/resolve",
    response_model=ResolveDuplicationResponse,
    dependencies=[Depends(require_role("reviewer"))],
)
def resolve_duplication(
    duplication_id: uuid.UUID,
    body: ResolveDuplicationRequest,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> ResolveDuplicationResponse:
    """Resolve a probable duplication (V5-S2).

    resolution: "confirmed" | "not_duplicate"
    DUP-4: Human resolution only.
    DUP-5: Audited.
    """
    try:
        result = duplication_service.resolve_duplication(
            duplication_id=duplication_id,
            owner_id=session.organization_id,
            user_id=session.user_id,
            resolution=body.resolution,
            reason=body.reason,
            db=db,
        )
    except ValueError as e:
        raise ConflictException(str(e))

    return ResolveDuplicationResponse(**result)
