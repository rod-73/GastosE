"""Manual correction service (E14, INV-7).

Provides:
- record_correction: create an append-only correction record.
- get_corrections: list corrections for an expense.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from backend.models.manual_correction import ManualCorrection
from backend.utils import uuid7


def record_correction(
    expense_id: uuid.UUID,
    owner_id: uuid.UUID,
    field: str,
    old_value: str,
    new_value: str,
    corrected_by: uuid.UUID,
    db: DbSession,
    reason: Optional[str] = None,
) -> ManualCorrection:
    """Record a manual correction (append-only, INV-7).

    INV-7: old_value and new_value are NOT NULL.
    """
    if not old_value:
        raise ValueError("old_value is required (INV-7)")
    if not new_value:
        raise ValueError("new_value is required (INV-7)")

    correction = ManualCorrection(
        id=uuid7(),
        owner_id=owner_id,
        expense_id=expense_id,
        field=field,
        old_value=old_value,
        new_value=new_value,
        corrected_by=corrected_by,
        corrected_at=datetime.now(timezone.utc),
        reason=reason,
    )
    db.add(correction)
    db.commit()
    db.refresh(correction)
    return correction


def get_corrections(
    expense_id: uuid.UUID,
    owner_id: uuid.UUID,
    db: DbSession,
) -> List[Dict]:
    """List all corrections for an expense."""
    corrections = (
        db.execute(
            select(ManualCorrection)
            .where(
                ManualCorrection.expense_id == expense_id,
                ManualCorrection.owner_id == owner_id,
            )
            .order_by(ManualCorrection.corrected_at)
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(c.id),
            "expense_id": str(c.expense_id),
            "field": c.field,
            "old_value": c.old_value,
            "new_value": c.new_value,
            "corrected_by": str(c.corrected_by),
            "corrected_at": c.corrected_at.isoformat() if c.corrected_at else None,
            "reason": c.reason,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in corrections
    ]
