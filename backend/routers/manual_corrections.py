"""Manual corrections router (E14, INV-7).

Endpoints:
- GET /api/v1/expenses/{expense_id}/corrections: list corrections.
"""
from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DbSession

from backend.database import get_db
from backend.middleware.auth import get_session, require_role
from backend.models.session import Session
from backend.schemas.manual_correction import ManualCorrectionResponse
from backend.services import manual_correction_service

router = APIRouter(tags=["manual-corrections"])


@router.get(
    "/api/v1/expenses/{expense_id}/corrections",
    response_model=List[ManualCorrectionResponse],
    dependencies=[Depends(require_role("reader"))],
)
def list_corrections(
    expense_id: uuid.UUID,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> List[ManualCorrectionResponse]:
    """List all manual corrections for an expense."""
    corrections = manual_correction_service.get_corrections(
        expense_id=expense_id,
        owner_id=session.organization_id,
        db=db,
    )
    return [ManualCorrectionResponse(**c) for c in corrections]
