"""Review service (V4-S1, V4-S2, V4-S3, V4-S4).

Provides:
- get_review_view: aggregate all five levels for a field (V4-S1).
- apply_review_decision: confirm/correct/reject a field (V4-S2).
- accept_expense: final validation + snapshot (V4-S3).
- reject_expense: terminal rejection (V4-S4).
- void_expense: void an accepted expense (V4-S4).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from backend.models.audit_event import AuditEvent
from backend.models.catalog import Supplier
from backend.models.document import SourceDocument
from backend.models.expense import Expense, ExpenseLine, TaxLine
from backend.models.extraction import Extraction, ExtractedValue
from backend.models.normalized_value import NormalizedValue
from backend.models.validated_value import ValidatedValue
from backend.utils import uuid7


def get_review_view(
    expense_id: uuid.UUID,
    owner_id: uuid.UUID,
    db: DbSession,
) -> Dict:
    """Build the review view for an expense (V4-S1).

    Returns a dict with:
    - expense: basic expense info.
    - fields: list of field-level review data (five levels).
    - document: source document info.
    """
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
        raise ValueError("Expense not found")

    # Get the document.
    doc = (
        db.execute(
            select(SourceDocument).where(
                SourceDocument.id == expense.document_id,
            )
        )
        .scalars()
        .first()
    )

    # Get the extraction for this document.
    extraction = (
        db.execute(
            select(Extraction)
            .where(
                Extraction.document_id == expense.document_id,
                Extraction.owner_id == owner_id,
            )
            .order_by(Extraction.created_at.desc())
        )
        .scalars()
        .first()
    )

    # Build field-level review data.
    fields: List[Dict] = []
    if extraction is not None:
        extracted_values = (
            db.execute(
                select(ExtractedValue).where(
                    ExtractedValue.extraction_id == extraction.id,
                )
            )
            .scalars()
            .all()
        )

        for ev in extracted_values:
            # Normalized value.
            nv = (
                db.execute(
                    select(NormalizedValue).where(
                        NormalizedValue.extracted_value_id == ev.id,
                    )
                )
                .scalars()
                .first()
            )

            # Validated value.
            vv = None
            if nv is not None:
                vv = (
                    db.execute(
                        select(ValidatedValue).where(
                            ValidatedValue.normalized_value_id == nv.id,
                        )
                    )
                    .scalars()
                    .first()
                )

            field_data = {
                "field": ev.field,
                "extracted": {
                    "value": ev.raw_value,
                    "confidence": float(ev.confidence) if ev.confidence is not None else None,
                    "provenance": ev.provenance,
                },
                "normalized": {
                    "value": nv.normalized_value if nv else None,
                    "rule": nv.normalization_rule if nv else None,
                },
                "validated": {
                    "value": vv.validated_value if vv else None,
                    "result": vv.validation_result if vv else None,
                    "rules_applied": json.loads(vv.rules_applied) if vv and vv.rules_applied else None,
                },
                "accepted": None,  # Filled from expense fields.
            }

            # Map to expense fields for the "accepted" level.
            if ev.field == "total_amount":
                field_data["accepted"] = {
                    "value": str(expense.total),
                    "source": "expense.total",
                }
            elif ev.field == "base_amount":
                field_data["accepted"] = {
                    "value": str(expense.base_total) if expense.base_total is not None else None,
                    "source": "expense.base_total",
                }
            elif ev.field == "vat_amount":
                field_data["accepted"] = {
                    "value": str(expense.vat_total) if expense.vat_total is not None else None,
                    "source": "expense.vat_total",
                }
            elif ev.field == "currency":
                field_data["accepted"] = {
                    "value": expense.currency,
                    "source": "expense.currency",
                }
            elif ev.field == "invoice_date":
                field_data["accepted"] = {
                    "value": expense.document_date.isoformat() if expense.document_date else None,
                    "source": "expense.document_date",
                }
            elif ev.field == "supplier_name":
                field_data["accepted"] = {
                    "value": expense.document_number,
                    "source": "expense.supplier",
                }

            fields.append(field_data)

    return {
        "expense": {
            "id": str(expense.id),
            "document_id": str(expense.document_id),
            "supplier_id": str(expense.supplier_id),
            "document_number": expense.document_number,
            "document_date": expense.document_date.isoformat() if expense.document_date else None,
            "currency": expense.currency,
            "base_total": str(expense.base_total) if expense.base_total is not None else None,
            "vat_total": str(expense.vat_total) if expense.vat_total is not None else None,
            "withholding_total": str(expense.withholding_total) if expense.withholding_total is not None else None,
            "total": str(expense.total),
            "state": expense.state,
        },
        "fields": fields,
        "document": {
            "id": str(doc.id) if doc else None,
            "fingerprint": doc.fingerprint_sha256 if doc else None,
            "format": doc.format_detected if doc else None,
            "size_bytes": doc.size_bytes if doc else None,
            "state": doc.state if doc else None,
        },
    }


def apply_review_decision(
    expense_id: uuid.UUID,
    owner_id: uuid.UUID,
    user_id: uuid.UUID,
    field: str,
    decision: str,
    corrected_value: Optional[str],
    reason: Optional[str],
    db: DbSession,
) -> Dict:
    """Apply a review decision to a field (V4-S2).

    decision: "confirm" | "correct" | "reject"
    - confirm: keep the validated value.
    - correct: set corrected_value as the new validated value.
    - reject: mark the field as rejected (expense goes to rejected state).

    Returns the updated field data.
    """
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
        raise ValueError("Expense not found")

    if expense.state not in ("draft", "under_review", "validation_error"):
        raise ValueError(
            f"Cannot review expense in state '{expense.state}'. "
            "Must be draft, under_review, or validation_error."
        )

    # Find the validated value for this field.
    vv = (
        db.execute(
            select(ValidatedValue)
            .join(NormalizedValue, ValidatedValue.normalized_value_id == NormalizedValue.id)
            .join(ExtractedValue, NormalizedValue.extracted_value_id == ExtractedValue.id)
            .join(Extraction, ExtractedValue.extraction_id == Extraction.id)
            .where(
                Extraction.document_id == expense.document_id,
                Extraction.owner_id == owner_id,
                ValidatedValue.field == field,
            )
        )
        .scalars()
        .first()
    )

    if vv is None:
        raise ValueError(f"No validated value found for field '{field}'")

    before = {
        "field": field,
        "validated_value": vv.validated_value,
        "validation_result": vv.validation_result,
    }

    if decision == "confirm":
        # Keep the validated value. No change needed.
        pass
    elif decision == "correct":
        if corrected_value is None:
            raise ValueError("corrected_value is required for 'correct' decision")
        vv.validated_value = corrected_value
        vv.validation_result = "corrected"
        # Update rules_applied to record the correction.
        try:
            rules = json.loads(vv.rules_applied) if vv.rules_applied else []
        except (json.JSONDecodeError, TypeError):
            rules = []
        rules.append({
            "rule_id": "MANUAL-CORRECTION",
            "severity": "INFO",
            "passed": True,
            "message": f"Corrected by user: {reason or 'no reason'}",
        })
        vv.rules_applied = json.dumps(rules)
    elif decision == "reject":
        # Mark the expense as rejected.
        expense.state = "rejected"
        expense.rejection_reason = reason or f"Field '{field}' rejected"
    else:
        raise ValueError(f"Unknown decision: {decision}")

    # Create audit event.
    audit = AuditEvent(
        id=uuid7(),
        owner_id=owner_id,
        entity_type="expense",
        entity_id=expense.id,
        action=f"review.{decision}",
        actor=user_id,
        before_data=before,
        after_data={
            "field": field,
            "validated_value": vv.validated_value,
            "validation_result": vv.validation_result,
            "expense_state": expense.state,
        },
    )
    db.add(audit)

    db.commit()
    db.refresh(expense)

    return {
        "field": field,
        "decision": decision,
        "validated_value": vv.validated_value,
        "validation_result": vv.validation_result,
        "expense_state": expense.state,
    }


def accept_expense(
    expense_id: uuid.UUID,
    owner_id: uuid.UUID,
    user_id: uuid.UUID,
    db: DbSession,
) -> Expense:
    """Accept an expense (V4-S3).

    Precondition: expense must be in a state that allows acceptance.
    Performs final validation, creates an immutable snapshot.
    """
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
        raise ValueError("Expense not found")

    if expense.state not in ("draft", "under_review", "ready_for_acceptance"):
        raise ValueError(
            f"Cannot accept expense in state '{expense.state}'. "
            "Must be draft, under_review, or ready_for_acceptance."
        )

    # Final validation: check INV-1.
    if expense.base_total is not None and expense.vat_total is not None:
        expected_total = expense.base_total + expense.vat_total
        if expense.withholding_total is not None:
            expected_total -= expense.withholding_total
        if abs(expense.total - expected_total) > Decimal("0.01"):
            raise ValueError(
                f"INV-1 violated on acceptance: total ({expense.total}) "
                f"!= base ({expense.base_total}) + vat ({expense.vat_total})"
            )

    # Check for probable duplicates.
    from backend.models.duplication import Duplication
    dup = (
        db.execute(
            select(Duplication).where(
                Duplication.owner_id == owner_id,
                Duplication.state == "probable",
                (
                    (Duplication.document_a_id == expense.document_id)
                    | (Duplication.document_b_id == expense.document_id)
                ),
            )
        )
        .scalars()
        .first()
    )
    if dup is not None:
        raise ValueError(
            "Cannot accept: probable duplicate exists. "
            "Resolve the duplication first."
        )

    # Create the snapshot (immutable).
    snapshot = {
        "expense_id": str(expense.id),
        "document_id": str(expense.document_id),
        "supplier_id": str(expense.supplier_id),
        "document_number": expense.document_number,
        "document_date": expense.document_date.isoformat() if expense.document_date else None,
        "currency": expense.currency,
        "base_total": str(expense.base_total) if expense.base_total is not None else None,
        "vat_total": str(expense.vat_total) if expense.vat_total is not None else None,
        "withholding_total": str(expense.withholding_total) if expense.withholding_total is not None else None,
        "total": str(expense.total),
        "state": "accepted",
        "accepted_at": datetime.now(timezone.utc).isoformat(),
        "accepted_by": str(user_id),
    }

    # Update the expense.
    before = {
        "state": expense.state,
        "accepted_snapshot": expense.accepted_snapshot,
    }
    expense.state = "accepted"
    expense.accepted_by = user_id
    expense.accepted_at = datetime.now(timezone.utc)
    expense.accepted_snapshot = json.dumps(snapshot)

    # Create audit event.
    audit = AuditEvent(
        id=uuid7(),
        owner_id=owner_id,
        entity_type="expense",
        entity_id=expense.id,
        action="accept",
        actor=user_id,
        before_data=before,
        after_data={"state": "accepted", "accepted_at": expense.accepted_at.isoformat()},
    )
    db.add(audit)

    db.commit()
    db.refresh(expense)
    return expense


def reject_expense(
    expense_id: uuid.UUID,
    owner_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: str,
    db: DbSession,
) -> Expense:
    """Reject an expense (V4-S4). Terminal action."""
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
        raise ValueError("Expense not found")

    if expense.state == "accepted":
        raise ValueError("Cannot reject an accepted expense. Use void instead.")

    if expense.state == "rejected":
        raise ValueError("Expense is already rejected.")

    before = {"state": expense.state}
    expense.state = "rejected"
    expense.rejection_reason = reason

    audit = AuditEvent(
        id=uuid7(),
        owner_id=owner_id,
        entity_type="expense",
        entity_id=expense.id,
        action="reject",
        actor=user_id,
        before_data=before,
        after_data={"state": "rejected", "reason": reason},
    )
    db.add(audit)

    db.commit()
    db.refresh(expense)
    return expense


def void_expense(
    expense_id: uuid.UUID,
    owner_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: str,
    db: DbSession,
) -> Expense:
    """Void an accepted expense (V4-S4)."""
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
        raise ValueError("Expense not found")

    if expense.state != "accepted":
        raise ValueError("Can only void an accepted expense.")

    before = {"state": expense.state}
    expense.state = "voided"
    expense.voided_by = user_id
    expense.voided_at = datetime.now(timezone.utc)
    expense.voided_reason = reason

    audit = AuditEvent(
        id=uuid7(),
        owner_id=owner_id,
        entity_type="expense",
        entity_id=expense.id,
        action="void",
        actor=user_id,
        before_data=before,
        after_data={"state": "voided", "reason": reason},
    )
    db.add(audit)

    db.commit()
    db.refresh(expense)
    return expense
