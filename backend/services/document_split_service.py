"""Document split service (E19, INV-4).

Provides:
- create_split: create a document split.
- add_expense_to_split: link an expense to a split.
- get_split: get a split with its expenses.
- list_splits: list splits for a document.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from backend.models.document import SourceDocument
from backend.models.document_split import DocumentSplit, SplitExpense
from backend.models.expense import Expense
from backend.utils import uuid7


def create_split(
    document_id: uuid.UUID,
    owner_id: uuid.UUID,
    created_by: uuid.UUID,
    justification: str,
    db: DbSession,
) -> DocumentSplit:
    """Create a document split (E19).

    INV-4: A document can feed multiple expenses via a split.
    """
    # Verify the document exists.
    document = (
        db.execute(
            select(SourceDocument).where(
                SourceDocument.id == document_id,
                SourceDocument.owner_id == owner_id,
            )
        )
        .scalars()
        .first()
    )
    if document is None:
        raise ValueError(f"Document {document_id} not found")

    # Check if a split already exists for this document.
    existing_split = (
        db.execute(
            select(DocumentSplit).where(
                DocumentSplit.document_id == document_id,
                DocumentSplit.owner_id == owner_id,
            )
        )
        .scalars()
        .first()
    )
    if existing_split is not None:
        raise ValueError(
            f"Document {document_id} already has a split. "
            f"Multiple splits per document are not supported in V1."
        )

    split = DocumentSplit(
        id=uuid7(),
        owner_id=owner_id,
        document_id=document_id,
        created_by=created_by,
        justification=justification,
    )
    db.add(split)
    db.commit()
    db.refresh(split)
    return split


def add_expense_to_split(
    split_id: uuid.UUID,
    expense_id: uuid.UUID,
    owner_id: uuid.UUID,
    db: DbSession,
) -> SplitExpense:
    """Link an expense to a split."""
    # Verify the split exists.
    split = (
        db.execute(
            select(DocumentSplit).where(
                DocumentSplit.id == split_id,
                DocumentSplit.owner_id == owner_id,
            )
        )
        .scalars()
        .first()
    )
    if split is None:
        raise ValueError(f"Split {split_id} not found")

    # Verify the expense exists.
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

    # Check if the expense is already linked.
    existing_link = (
        db.execute(
            select(SplitExpense).where(
                SplitExpense.split_id == split_id,
                SplitExpense.expense_id == expense_id,
            )
        )
        .scalars()
        .first()
    )
    if existing_link is not None:
        raise ValueError(
            f"Expense {expense_id} is already linked to split {split_id}"
        )

    link = SplitExpense(
        split_id=split_id,
        expense_id=expense_id,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def get_split(
    split_id: uuid.UUID,
    owner_id: uuid.UUID,
    db: DbSession,
) -> Optional[Dict]:
    """Get a split with its expenses."""
    split = (
        db.execute(
            select(DocumentSplit).where(
                DocumentSplit.id == split_id,
                DocumentSplit.owner_id == owner_id,
            )
        )
        .scalars()
        .first()
    )
    if split is None:
        return None

    # Get linked expenses.
    links = (
        db.execute(
            select(SplitExpense).where(SplitExpense.split_id == split_id)
        )
        .scalars()
        .all()
    )
    expense_ids = [link.expense_id for link in links]

    expenses = (
        db.execute(
            select(Expense).where(Expense.id.in_(expense_ids))
        )
        .scalars()
        .all()
    )

    return {
        "id": str(split.id),
        "document_id": str(split.document_id),
        "created_by": str(split.created_by),
        "justification": split.justification,
        "created_at": split.created_at.isoformat() if split.created_at else None,
        "expenses": [
            {
                "id": str(e.id),
                "total": str(e.total),
                "state": e.state,
            }
            for e in expenses
        ],
    }


def list_splits(
    document_id: uuid.UUID,
    owner_id: uuid.UUID,
    db: DbSession,
) -> List[Dict]:
    """List splits for a document."""
    splits = (
        db.execute(
            select(DocumentSplit).where(
                DocumentSplit.document_id == document_id,
                DocumentSplit.owner_id == owner_id,
            )
        )
        .scalars()
        .all()
    )

    result = []
    for split in splits:
        split_data = get_split(split.id, owner_id, db)
        if split_data:
            result.append(split_data)

    return result
