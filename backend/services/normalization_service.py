"""Normalization service (V3-S1, N3).

Deterministic normalization of extracted values:
- Currency: ISO-4217 code, decimal exact (NUMERIC).
- Date: ISO-8601 (YYYY-MM-DD).
- NIF/CIF: validated (check digit).
- Tax rate: known Spanish VAT rates.

Each normalized value references its extraction origin (INV-10).
Values that cannot be normalized are marked as 'uncertain' (not stored
as normalized; the document state transitions to 'uncertain').
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from backend.models.extraction import Extraction, ExtractedValue
from backend.models.normalized_value import NormalizedValue
from backend.utils import uuid7


@dataclass
class NormalizationResult:
    """Result of normalizing a single field."""

    field: str
    raw_value: str
    normalized_value: Optional[str]
    rule: str
    success: bool
    error: Optional[str] = None


# --- Normalization rules ---


def normalize_currency(raw: str) -> Tuple[Optional[str], str, Optional[str]]:
    """Normalize a currency code to ISO-4217.

    Accepts: 'EUR', 'eur', 'Euro', '€', '123.45 EUR', etc.
    Returns: (normalized_code, rule, error)
    """
    raw = raw.strip().upper()

    # Direct ISO code.
    if re.match(r"^[A-Z]{3}$", raw):
        return raw, "currency.iso4217", None

    # Common Spanish currency names.
    currency_map = {
        "EURO": "EUR",
        "EUR": "EUR",
        "€": "EUR",
        "DOLAR": "USD",
        "DÓLAR": "USD",
        "USD": "USD",
        "$": "USD",
        "LIBRA": "GBP",
        "GBP": "GBP",
        "£": "GBP",
    }
    if raw in currency_map:
        return currency_map[raw], "currency.name_to_iso", None

    # Try to extract a 3-letter code from the string.
    m = re.search(r"([A-Z]{3})", raw)
    if m:
        return m.group(1), "currency.extract_iso", None

    return None, "currency.iso4217", f"Cannot normalize currency: {raw!r}"


def normalize_amount(raw: str) -> Tuple[Optional[str], str, Optional[str]]:
    """Normalize a monetary amount to a decimal string (exact).

    Accepts: '123.45', '1.234,56', '1234,56', '1,234.56', etc.
    Returns: (normalized_amount, rule, error)
    """
    raw = raw.strip()

    # Remove currency symbols and spaces.
    cleaned = re.sub(r"[€$£\s]", "", raw)

    # Simple decimal: 123.45 or 123,45 (no thousands separator).
    if re.match(r"^\d+([.,]\d{1,2})?$", cleaned):
        normalized = cleaned.replace(",", ".")
        return normalized, "amount.simple_decimal", None

    # Spanish format: 1.234,56 (dot=thousands, comma=decimal).
    if re.match(r"^\d{1,3}(\.\d{3})*(,\d{1,2})?$", cleaned):
        # Convert: remove dots, replace comma with dot.
        normalized = cleaned.replace(".", "").replace(",", ".")
        return normalized, "amount.es_format", None

    # US format: 1,234.56 (comma=thousands, dot=decimal).
    if re.match(r"^\d{1,3}(,\d{3})*(\.\d{1,2})?$", cleaned):
        normalized = cleaned.replace(",", "")
        return normalized, "amount.us_format", None

    # Integer: 123.
    if re.match(r"^\d+$", cleaned):
        return cleaned + ".00", "amount.integer_to_decimal", None

    return None, "amount.decimal_exact", f"Cannot normalize amount: {raw!r}"


def normalize_date(raw: str) -> Tuple[Optional[str], str, Optional[str]]:
    """Normalize a date to ISO-8601 (YYYY-MM-DD).

    Accepts: '2024-01-15', '15/01/2024', '15-01-2024', '15 Jan 2024', etc.
    Returns: (normalized_date, rule, error)
    """
    raw = raw.strip()

    # Already ISO.
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        try:
            datetime.strptime(raw, "%Y-%m-%d")
            return raw, "date.iso8601", None
        except ValueError:
            pass

    # Spanish format: DD/MM/YYYY or DD-MM-YYYY.
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", raw)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            dt = datetime(year, month, day)
            return dt.strftime("%Y-%m-%d"), "date.es_format", None
        except ValueError:
            return None, "date.iso8601", f"Invalid date: {raw!r}"

    # US format: MM/DD/YYYY.
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", raw)
    if m:
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            dt = datetime(year, month, day)
            return dt.strftime("%Y-%m-%d"), "date.us_format", None
        except ValueError:
            return None, "date.iso8601", f"Invalid date: {raw!r}"

    # ISO with time: 2024-01-15T10:30:00.
    m = re.match(r"^(\d{4}-\d{2}-\d{2})T", raw)
    if m:
        return m.group(1), "date.iso8601_strip_time", None

    return None, "date.iso8601", f"Cannot normalize date: {raw!r}"


def normalize_nif(raw: str) -> Tuple[Optional[str], str, Optional[str]]:
    """Validate and normalize a Spanish NIF/CIF.

    NIF: 8 digits + 1 letter (DNI).
    CIF: 1 letter + 7 digits + 1 check char.
    Returns: (normalized_nif, rule, error)
    """
    raw = raw.strip().upper()

    # NIF (DNI): 8 digits + letter.
    if re.match(r"^\d{8}[A-Z]$", raw):
        # Validate check letter.
        if _validate_nif_check(raw):
            return raw, "nif.dni_validated", None
        return None, "nif.dni_validated", f"Invalid NIF check digit: {raw!r}"

    # NIE: X/Y/Z + exactly 7 digits + letter (check before CIF since
    # X/Y/Z are also valid CIF prefixes).
    if re.match(r"^[XYZ]\d{7}[A-Z]$", raw):
        return raw, "nif.nie_accepted", None

    # CIF: letter + 7 digits + check.
    if re.match(r"^[A-Z]\d{7}[A-Z0-9]$", raw):
        # Validate check character.
        if _validate_cif_check(raw):
            return raw, "nif.cif_validated", None
        return None, "nif.cif_validated", f"Invalid CIF check: {raw!r}"

    return None, "nif.validation", f"Cannot normalize NIF/CIF: {raw!r}"


def normalize_vat_rate(raw: str) -> Tuple[Optional[str], str, Optional[str]]:
    """Normalize a VAT rate to a known Spanish rate.

    Known rates: 0, 4, 10, 21.
    Returns: (normalized_rate, rule, error)
    """
    raw = raw.strip().replace("%", "").replace(",", ".")

    try:
        rate = float(raw)
    except ValueError:
        return None, "vat.known_rate", f"Cannot parse VAT rate: {raw!r}"

    known_rates = {0.0, 4.0, 10.0, 21.0}
    if rate in known_rates:
        # Format: integer if whole, else 1 decimal.
        if rate == int(rate):
            return str(int(rate)), "vat.known_rate", None
        return f"{rate:.1f}", "vat.known_rate", None

    return None, "vat.known_rate", f"Unknown VAT rate: {rate} (expected 0, 4, 10, 21)"


# --- NIF/CIF validation helpers ---

_NIF_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"


def _validate_nif_check(nif: str) -> bool:
    """Validate the check letter of a DNI/NIF."""
    digits = nif[:-1]
    check_letter = nif[-1]
    expected = _NIF_LETTERS[int(digits) % 23]
    return check_letter == expected


def _validate_cif_check(cif: str) -> bool:
    """Validate the check character of a CIF."""
    body = cif[1:-1]  # 7 digits
    check = cif[-1]

    # Sum of digits in odd positions (1st, 3rd, 5th, 7th).
    odd_sum = sum(int(body[i]) for i in range(0, 7, 2))

    # Even positions: double each digit, sum digits of result.
    even_sum = 0
    for i in range(1, 7, 2):
        doubled = int(body[i]) * 2
        even_sum += doubled // 10 + doubled % 10

    total = odd_sum + even_sum
    control_digit = (10 - (total % 10)) % 10

    # The check can be a digit or a letter (for certain prefixes).
    if check == str(control_digit):
        return True

    # For CIFs starting with A, B, H, J, P, Q: check is a letter.
    if cif[0] in "ABHJPQ":
        letter = _NIF_LETTERS[control_digit]
        return check == letter

    return False


# --- Field-specific normalization dispatcher ---

# Maps field name -> (normalization function, rule prefix).
FIELD_NORMALIZERS = {
    "currency": normalize_currency,
    "total_amount": normalize_amount,
    "base_amount": normalize_amount,
    "vat_amount": normalize_amount,
    "invoice_date": normalize_date,
    "supplier_nif": normalize_nif,
    "vat_rate": normalize_vat_rate,
}

# Fields that don't need normalization (pass-through).
PASSTHROUGH_FIELDS = {
    "supplier_name",
    "invoice_number",
    "payment_method",
    "description",
}


def normalize_field(field: str, raw_value: str) -> NormalizationResult:
    """Normalize a single field value.

    Returns a NormalizationResult with success/failure.
    """
    if field in PASSTHROUGH_FIELDS:
        return NormalizationResult(
            field=field,
            raw_value=raw_value,
            normalized_value=raw_value,
            rule="passthrough",
            success=True,
        )

    if field in FIELD_NORMALIZERS:
        normalizer = FIELD_NORMALIZERS[field]
        normalized, rule, error = normalizer(raw_value)
        return NormalizationResult(
            field=field,
            raw_value=raw_value,
            normalized_value=normalized,
            rule=rule,
            success=normalized is not None,
            error=error,
        )

    # Unknown field: pass through.
    return NormalizationResult(
        field=field,
        raw_value=raw_value,
        normalized_value=raw_value,
        rule="passthrough_unknown",
        success=True,
    )


def normalize_extraction(
    extraction_id: uuid.UUID,
    owner_id: uuid.UUID,
    db: DbSession,
) -> Tuple[int, int]:
    """Normalize all extracted values for a given extraction.

    Creates NormalizedValue records (E4) for each successfully
    normalized field. Fields that cannot be normalized are skipped
    (the document will be marked 'uncertain' by the caller).

    Returns (normalized_count, failed_count).
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

    # Get all extracted values.
    values = (
        db.execute(
            select(ExtractedValue).where(
                ExtractedValue.extraction_id == extraction_id,
            )
        )
        .scalars()
        .all()
    )

    normalized_count = 0
    failed_count = 0

    for ev in values:
        result = normalize_field(ev.field, ev.raw_value)

        if result.success and result.normalized_value is not None:
            nv = NormalizedValue(
                id=uuid7(),
                owner_id=owner_id,
                extracted_value_id=ev.id,
                field=ev.field,
                normalized_value=result.normalized_value,
                normalization_rule=result.rule,
            )
            db.add(nv)
            normalized_count += 1
        else:
            failed_count += 1

    db.commit()
    return normalized_count, failed_count
