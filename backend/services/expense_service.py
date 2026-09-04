"""Expense creation service (V3-S3).

Creates an expense (E6) from validated values, including:
- Expense line (E7) for the base amount.
- Tax line (E8) for VAT.

INV-1: total == base + IVA - retenciones.
INV-3: document_id NOT NULL.
INV-13: Single currency.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from backend.models.document import SourceDocument
from backend.models.expense import Expense, ExpenseLine, TaxLine
from backend.models.extraction import Extraction, ExtractedValue
from backend.models.normalized_value import NormalizedValue
from backend.models.validated_value import ValidatedValue
from backend.utils import uuid7


def _find_tax_rate_id(
    db: DbSession,
    owner_id: uuid.UUID,
    rate_str: str,
) -> Optional[uuid.UUID]:
    """Find the tax rate ID for a given rate value.

    tax_rates table columns: id, owner_id, code, description, tax_type,
    percentage, valid_from, valid_until, jurisdiction, created_at, updated_at.
    """
    from backend.models.catalog import TaxRate

    try:
        rate = Decimal(rate_str)
    except (InvalidOperation, TypeError):
        return None

    result = db.execute(
        select(TaxRate).where(
            TaxRate.owner_id == owner_id,
            TaxRate.percentage == rate,
            TaxRate.tax_type == "vat",
        )
    )
    row = result.scalars().first()
    if row:
        return row.id
    return None


def create_expense_from_validation(
    extraction_id: uuid.UUID,
    owner_id: uuid.UUID,
    db: DbSession,
) -> Expense:
    """Create an expense (E6) from validated values.

    Reads validated values (E5) and creates:
    - Expense (E6) with totals.
    - Expense line (E7) for the base amount.
    - Tax line (E8) for VAT.

    Precondition: validation must have been run (E5 records exist).
    All BLOCK rules must have passed.

    Returns the created Expense.
    Raises ValueError if preconditions are not met.
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
        raise ValueError("Extraction not found")

    # Get validated values.
    validated_values = (
        db.execute(
            select(ValidatedValue)
            .where(
                ValidatedValue.normalized_value_id.in_(
                    select(NormalizedValue.id).where(
                        NormalizedValue.extracted_value_id.in_(
                            select(ExtractedValue.id).where(
                                ExtractedValue.extraction_id == extraction_id
                            )
                        )
                    )
                )
            )
        )
        .scalars()
        .all()
    )

    if not validated_values:
        raise ValueError("No validated values found. Run validation first.")

    # Check for BLOCK failures.
    failed = [vv for vv in validated_values if vv.validation_result == "failed"]
    if failed:
        raise ValueError(
            f"Validation has BLOCK failures: {', '.join(vv.field for vv in failed)}. "
            "Cannot create expense with failed validation."
        )

    # Build values dict.
    values: Dict[str, str] = {
        vv.field: vv.validated_value for vv in validated_values
    }

    # Extract required fields.
    supplier_name = values.get("supplier_name", "Unknown")
    total_str = values.get("total_amount", "0")
    base_str = values.get("base_amount", "0")
    vat_str = values.get("vat_amount", "0")
    currency = values.get("currency", "EUR")
    date_str = values.get("invoice_date", "")
    vat_rate_str = values.get("vat_rate", "21")
    doc_number = values.get("invoice_number", "")

    try:
        total = Decimal(total_str)
        base = Decimal(base_str)
        vat = Decimal(vat_str)
    except (InvalidOperation, TypeError) as e:
        raise ValueError(f"Cannot parse amounts: {e}")

    # Verify INV-1: total == base + vat (simplified, no withholding for now).
    if abs(total - (base + vat)) > Decimal("0.01"):
        raise ValueError(
            f"INV-1 violated: total ({total}) != base ({base}) + vat ({vat})"
        )

    # Parse date.
    doc_date: Optional[date] = None
    if date_str:
        try:
            doc_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            doc_date = None

    # Get the document.
    doc = (
        db.execute(
            select(SourceDocument).where(
                SourceDocument.id == extraction.document_id,
            )
        )
        .scalars()
        .first()
    )
    if doc is None:
        raise ValueError("Source document not found")

    # Find or create supplier.
    # For now, we look up by NIF or create a placeholder.
    # In a full implementation, this would use the supplier service.
    supplier_id = _find_or_create_supplier(
        db, owner_id, supplier_name, values.get("supplier_nif", "")
    )

    # Find tax rate.
    from backend.models.catalog import TaxRate

    tax_rate_id = _find_tax_rate_id(db, owner_id, vat_rate_str)
    if tax_rate_id is None:
        # Fallback: find any VAT tax rate for the org.
        result = db.execute(
            select(TaxRate).where(
                TaxRate.owner_id == owner_id,
                TaxRate.tax_type == "vat",
            )
        )
        row = result.scalars().first()
        if row:
            tax_rate_id = row.id
        else:
            raise ValueError("No active tax rate found")

    # Create the expense.
    expense = Expense(
        id=uuid7(),
        owner_id=owner_id,
        document_id=doc.id,
        supplier_id=supplier_id,
        document_number=doc_number or None,
        document_date=doc_date,
        currency=currency,
        base_total=base,
        vat_total=vat,
        withholding_total=Decimal("0"),
        total=total,
        state="draft",
    )
    db.add(expense)
    db.flush()

    # Create expense line (E7).
    line = ExpenseLine(
        id=uuid7(),
        owner_id=owner_id,
        expense_id=expense.id,
        description=supplier_name,
        quantity=Decimal("1"),
        amount=base,
        tax_rate_id=tax_rate_id,
    )
    db.add(line)
    db.flush()

    # Create tax line (E8) for VAT.
    tax_line = TaxLine(
        id=uuid7(),
        owner_id=owner_id,
        expense_line_id=line.id,
        expense_id=expense.id,
        tax_type="vat",
        tax_rate_id=tax_rate_id,
        taxable_base=base,
        tax_amount=vat,
    )
    db.add(tax_line)

    # Update document state.
    doc.state = "validated"
    db.commit()
    db.refresh(expense)

    return expense


def _find_or_create_supplier(
    db: DbSession,
    owner_id: uuid.UUID,
    name: str,
    nif: str,
) -> uuid.UUID:
    """Find an existing supplier by NIF/CIF or create a new one.

    suppliers table columns: id, owner_id, legal_name, nif_cif, tax_address,
    contact_data, state, created_at, updated_at.
    """
    from backend.models.catalog import Supplier

    # Try to find by NIF/CIF.
    if nif:
        result = db.execute(
            select(Supplier).where(
                Supplier.owner_id == owner_id,
                Supplier.nif_cif == nif,
            )
        )
        row = result.scalars().first()
        if row:
            return row.id

    # Try to find by legal name.
    result = db.execute(
        select(Supplier).where(
            Supplier.owner_id == owner_id,
            Supplier.legal_name == name,
        )
    )
    row = result.scalars().first()
    if row:
        return row.id

    # Create a new supplier.
    new_supplier = Supplier(
        id=uuid7(),
        owner_id=owner_id,
        legal_name=name,
        nif_cif=nif or "UNKNOWN",
        state="active",
    )
    db.add(new_supplier)
    db.flush()
    return new_supplier.id
