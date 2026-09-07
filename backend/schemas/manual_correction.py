"""Pydantic schemas for manual corrections (E14)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ManualCorrectionResponse(BaseModel):
    """Response schema for a manual correction."""

    id: str
    expense_id: str
    field: str
    old_value: str
    new_value: str
    corrected_by: str
    corrected_at: Optional[datetime] = None
    reason: Optional[str] = None
    created_at: Optional[datetime] = None
