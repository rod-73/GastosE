"""Duplication detection and query service (V5-S1, V5-S2).

Implements:
- build_dup_key: construct the logical duplication key (DUP-2).
- detect_logical_duplicates: find existing documents/expenses with the same
  dup_key and create Duplication records (DUP-2/3).
- list_duplications: list duplications for an organization.
- get_duplication: get a single duplication with document details.
- resolve_duplication: resolve a probable duplication (V5-S2).

DUP-2: Key = (supplier, document_number, date, total_amount).
For tickets without a document number, the key is (supplier, date, total_amount)
and detection is marked as less reliable.

DUP-3: Detection happens at extraction completion (when supplier, number,
date, and amount are available).

DUP-9: Fingerprint has priority — if fingerprints match, the duplication is
of type `fingerprint` (more reliable) even if the key also matches.

DUP-10: A document can have multiple probable duplications (with different
other documents); each is resolved separately.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from backend.models.audit_event import AuditEvent
from backend.models.duplication import Duplication
from backend.models.document import SourceDocument
from backend.models.expense import Expense
from backend.models.extraction import Extraction, ExtractedValue
from backend.models.normalized_value import NormalizedValue
from backend.models.validated_value import ValidatedValue
from backend.utils import uuid7


def build_dup_key(
    supplier: str,
    document_number: Optional[str],
    date_str: Optional[str],
    total_amount: Optional[str],
) -> str:
    """Build the logical duplication key (DUP-2).

    Key format: "supplier|document_number|date|total_amount"
    For tickets without a document number: "supplier||date|total_amount"

    All components are lowercased and stripped for normalization.
    Missing components are represented as empty strings.
    """
    s = (supplier or "").strip().lower()
    d = (document_number or "").strip().lower()
    dt = (date_str or "").strip()
    t = (total_amount or "").strip()
    return f"{s}|{d}|{dt}|{t}"


def _extract_field_values(
    extraction_id: uuid.UUID,
    db: DbSession,
) -> Dict[str, str]:
    """Extract field values from an extraction (raw values)."""
    values: Dict[str, str] = {}
    evs = (
        db.execute(
            select(ExtractedValue).where(
                ExtractedValue.extraction_id == extraction_id,
            )
        )
        .scalars()
        .all()
    )
    for ev in evs:
        values[ev.field] = ev.raw_value
    return values


def detect_logical_duplicates(
    extraction_id: uuid.UUID,
    owner_id: uuid.UUID,
    db: DbSession,
) -> List[Duplication]:
    """Detect logical duplicates for a completed extraction (DUP-2/3).

    Builds the dup_key from extracted values and searches for existing
    documents or expenses with the same key. Creates Duplication records
    for each match found.

    Returns the list of newly created Duplication records.
    """
    # Get the extraction.
    extraction = (
        db.execute(
            select(Extraction).where(
                Extraction.id == extraction_id,
                Extraction.owner_id == owner_id,
            )
        )
        .scalars()
        .first()
    )
    if extraction is None:
        return []

    # Extract field values.
    values = _extract_field_values(extraction_id, db)

    supplier = values.get("supplier_name", "")
    doc_number = values.get("invoice_number", "")
    date_str = values.get("invoice_date", "")
    total_str = values.get("total_amount", "")

    if not supplier or not total_str:
        # Cannot build a meaningful key without supplier and total.
        return []

    dup_key = build_dup_key(supplier, doc_number, date_str, total_str)

    # Store the dup_key on the document.
    doc = (
        db.execute(
            select(SourceDocument).where(
                SourceDocument.id == extraction.document_id,
            )
        )
        .scalars()
        .first()
    )
    if doc is not None:
        doc.dup_key = dup_key

    # Search for existing documents with the same dup_key.
    existing_docs = (
        db.execute(
            select(SourceDocument).where(
                SourceDocument.owner_id == owner_id,
                SourceDocument.dup_key == dup_key,
                SourceDocument.id != extraction.document_id,
                SourceDocument.dup_key.isnot(None),
            )
        )
        .scalars()
        .all()
    )

    # Search for existing expenses with matching fields.
    existing_expenses = (
        db.execute(
            select(Expense).where(
                Expense.owner_id == owner_id,
                Expense.document_id != extraction.document_id,
            )
        )
        .scalars()
        .all()
    )

    # Filter expenses by matching dup_key components.
    matching_expense_docs: List[SourceDocument] = []
    for exp in existing_expenses:
        exp_doc = (
            db.execute(
                select(SourceDocument).where(
                    SourceDocument.id == exp.document_id,
                )
            )
            .scalars()
            .first()
        )
        if exp_doc is not None and exp_doc.dup_key == dup_key:
            matching_expense_docs.append(exp_doc)

    # Combine and deduplicate.
    all_matches: List[SourceDocument] = list(existing_docs)
    seen_ids = {d.id for d in all_matches}
    for md in matching_expense_docs:
        if md.id not in seen_ids:
            all_matches.append(md)
            seen_ids.add(md.id)

    # Create Duplication records.
    created: List[Duplication] = []
    for match in all_matches:
        # Check if a duplication already exists (idempotency).
        existing_dup = (
            db.execute(
                select(Duplication).where(
                    Duplication.owner_id == owner_id,
                    (
                        (Duplication.document_a_id == extraction.document_id)
                        & (Duplication.document_b_id == match.id)
                    )
                    | (
                        (Duplication.document_a_id == match.id)
                        & (Duplication.document_b_id == extraction.document_id)
                    ),
                )
            )
            .scalars()
            .first()
        )
        if existing_dup is not None:
            continue

        # DUP-9: Check if fingerprints match (priority).
        dup_type = "logical"
        if doc is not None and match.fingerprint_sha256 == doc.fingerprint_sha256:
            dup_type = "fingerprint"

        dup = Duplication(
            id=uuid7(),
            owner_id=owner_id,
            document_a_id=extraction.document_id,
            document_b_id=match.id,
            dup_type=dup_type,
            state="probable",
        )
        db.add(dup)
        created.append(dup)

    if created:
        # Audit event.
        audit = AuditEvent(
            id=uuid7(),
            owner_id=owner_id,
            entity_type="duplication",
            entity_id=created[0].id,
            action="duplication.detected",
            actor=uuid.UUID(int=0),  # System
            after_data={
                "extraction_id": str(extraction_id),
                "dup_key": dup_key,
                "duplicates_found": len(created),
            },
        )
        db.add(audit)

    db.commit()
    return created


def list_duplications(
    owner_id: uuid.UUID,
    db: DbSession,
    state: Optional[str] = None,
) -> List[Dict]:
    """List duplications for an organization.

    Optionally filter by state.
    """
    query = select(Duplication).where(Duplication.owner_id == owner_id)
    if state is not None:
        query = query.where(Duplication.state == state)

    dups = (
        db.execute(query.order_by(Duplication.created_at.desc()))
        .scalars()
        .all()
    )

    results: List[Dict] = []
    for dup in dups:
        doc_a = (
            db.execute(
                select(SourceDocument).where(
                    SourceDocument.id == dup.document_a_id,
                )
            )
            .scalars()
            .first()
        )
        doc_b = (
            db.execute(
                select(SourceDocument).where(
                    SourceDocument.id == dup.document_b_id,
                )
            )
            .scalars()
            .first()
        )

        results.append({
            "id": str(dup.id),
            "document_a_id": str(dup.document_a_id),
            "document_b_id": str(dup.document_b_id),
            "document_a_fingerprint": doc_a.fingerprint_sha256 if doc_a else None,
            "document_b_fingerprint": doc_b.fingerprint_sha256 if doc_b else None,
            "document_a_state": doc_a.state if doc_a else None,
            "document_b_state": doc_b.state if doc_b else None,
            "dup_type": dup.dup_type,
            "state": dup.state,
            "resolved_by": str(dup.resolved_by) if dup.resolved_by else None,
            "resolved_at": dup.resolved_at.isoformat() if dup.resolved_at else None,
            "resolution_reason": dup.resolution_reason,
            "created_at": dup.created_at.isoformat() if dup.created_at else "",
        })

    return results


def get_duplication(
    duplication_id: uuid.UUID,
    owner_id: uuid.UUID,
    db: DbSession,
) -> Dict:
    """Get a single duplication with document details.

    Raises ValueError if not found.
    """
    dup = (
        db.execute(
            select(Duplication).where(
                Duplication.id == duplication_id,
                Duplication.owner_id == owner_id,
            )
        )
        .scalars()
        .first()
    )
    if dup is None:
        raise ValueError("Duplication not found")

    doc_a = (
        db.execute(
            select(SourceDocument).where(
                SourceDocument.id == dup.document_a_id,
            )
        )
        .scalars()
        .first()
    )
    doc_b = (
        db.execute(
            select(SourceDocument).where(
                SourceDocument.id == dup.document_b_id,
            )
        )
        .scalars()
        .first()
    )

    return {
        "id": str(dup.id),
        "document_a_id": str(dup.document_a_id),
        "document_b_id": str(dup.document_b_id),
        "document_a": {
            "id": str(doc_a.id) if doc_a else None,
            "fingerprint": doc_a.fingerprint_sha256 if doc_a else None,
            "format": doc_a.format_detected if doc_a else None,
            "size_bytes": doc_a.size_bytes if doc_a else None,
            "state": doc_a.state if doc_a else None,
            "dup_key": doc_a.dup_key if doc_a else None,
        },
        "document_b": {
            "id": str(doc_b.id) if doc_b else None,
            "fingerprint": doc_b.fingerprint_sha256 if doc_b else None,
            "format": doc_b.format_detected if doc_b else None,
            "size_bytes": doc_b.size_bytes if doc_b else None,
            "state": doc_b.state if doc_b else None,
            "dup_key": doc_b.dup_key if doc_b else None,
        },
        "dup_type": dup.dup_type,
        "state": dup.state,
        "resolved_by": str(dup.resolved_by) if dup.resolved_by else None,
        "resolved_at": dup.resolved_at.isoformat() if dup.resolved_at else None,
        "resolution_reason": dup.resolution_reason,
        "created_at": dup.created_at.isoformat() if dup.created_at else "",
    }


def resolve_duplication(
    duplication_id: uuid.UUID,
    owner_id: uuid.UUID,
    user_id: uuid.UUID,
    resolution: str,
    reason: str,
    db: DbSession,
) -> Dict:
    """Resolve a probable duplication (V5-S2, DUP-4..10).

    resolution: "confirmed" | "not_duplicate"
    - confirmed: the documents are the same purchase (terminal).
    - not_duplicate: the documents are different purchases (terminal).

    DUP-4: Human resolution only (no automatic resolution).
    DUP-5: Audited (user, timestamp, decision, reason).
    DUP-7: Reversibility limited — if an accepted expense is affected,
           the resolution is not reversed.
    DUP-8: Confirmed duplicate cannot be accepted.

    Raises ValueError if the duplication is not in 'probable' state.
    """
    dup = (
        db.execute(
            select(Duplication).where(
                Duplication.id == duplication_id,
                Duplication.owner_id == owner_id,
            )
        )
        .scalars()
        .first()
    )
    if dup is None:
        raise ValueError("Duplication not found")

    if dup.state != "probable":
        raise ValueError(
            f"Cannot resolve duplication in state '{dup.state}'. "
            "Only 'probable' duplications can be resolved."
        )

    if resolution not in ("confirmed", "not_duplicate"):
        raise ValueError(
            f"Invalid resolution: '{resolution}'. "
            "Must be 'confirmed' or 'not_duplicate'."
        )

    if not reason or not reason.strip():
        raise ValueError("Resolution reason is required.")

    before = {
        "state": dup.state,
        "resolved_by": str(dup.resolved_by) if dup.resolved_by else None,
    }

    now = datetime.now(timezone.utc)
    dup.state = resolution
    dup.resolved_by = user_id
    dup.resolved_at = now
    dup.resolution_reason = reason.strip()

    # If confirmed, mark the second document/expense as confirmed_duplicate.
    if resolution == "confirmed":
        # The "second" document is document_b (the one detected as duplicate).
        doc_b = (
            db.execute(
                select(SourceDocument).where(
                    SourceDocument.id == dup.document_b_id,
                )
            )
            .scalars()
            .first()
        )
        if doc_b is not None:
            doc_b.state = "confirmed_duplicate"

        # Mark any expense for document_b as confirmed_duplicate.
        expense = (
            db.execute(
                select(Expense).where(
                    Expense.document_id == dup.document_b_id,
                    Expense.owner_id == owner_id,
                )
            )
            .scalars()
            .first()
        )
        if expense is not None and expense.state not in ("accepted", "voided"):
            expense.state = "confirmed_duplicate"

    # If not_duplicate, restore document/expense to previous state.
    elif resolution == "not_duplicate":
        doc_b = (
            db.execute(
                select(SourceDocument).where(
                    SourceDocument.id == dup.document_b_id,
                )
            )
            .scalars()
            .first()
        )
        if doc_b is not None and doc_b.state == "confirmed_duplicate":
            # Restore to a reasonable state.
            doc_b.state = "extracted"

        expense = (
            db.execute(
                select(Expense).where(
                    Expense.document_id == dup.document_b_id,
                    Expense.owner_id == owner_id,
                )
            )
            .scalars()
            .first()
        )
        if expense is not None and expense.state == "confirmed_duplicate":
            expense.state = "draft"

    # Audit event (DUP-5).
    audit = AuditEvent(
        id=uuid7(),
        owner_id=owner_id,
        entity_type="duplication",
        entity_id=dup.id,
        action=f"duplication.resolved.{resolution}",
        actor=user_id,
        before_data=before,
        after_data={
            "state": dup.state,
            "resolved_by": str(user_id),
            "resolved_at": now.isoformat(),
            "reason": reason.strip(),
        },
    )
    db.add(audit)

    db.commit()
    db.refresh(dup)

    return {
        "id": str(dup.id),
        "state": dup.state,
        "resolved_by": str(dup.resolved_by),
        "resolved_at": dup.resolved_at.isoformat() if dup.resolved_at else None,
        "resolution_reason": dup.resolution_reason,
    }
