"""Extraction quality gate.

Evaluates the quality of deterministic extraction output BEFORE deciding
whether LLM fallback is needed.

The quality gate checks:
1. Presence: required fields are present.
2. Parseability: field values can be parsed by the normalizers.
3. Format: values conform to expected formats.
4. Arithmetic consistency: total ≈ base + vat (when all three are present).

This is NOT a replacement for the final validation (VR rules). It is a
pre-check that determines whether the deterministic result is "good enough"
to proceed without LLM, or whether the LLM should be invoked with the full
document context.

Design principles:
- No supplier-specific rules.
- No hardcoded values beyond what the normalizers already define.
- A field is "invalid" if the normalizer cannot process it.
- A field is "missing" if absent or has an empty/junk value.
- Arithmetic check only applies when total, base, and vat_amount are ALL
  present and parseable.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from backend.services.extraction_schema import REQUIRED_FIELDS, VALID_FIELDS
from backend.services.normalization_service import (
    FIELD_NORMALIZERS,
    PASSTHROUGH_FIELDS,
    normalize_field,
)

logger = logging.getLogger(__name__)


# Values that indicate a field was "captured" but is junk.
JUNK_VALUES = frozenset((".", "-", "N/A", "null", "", "n/a", "N/A", "—", "--"))


@dataclass
class FieldQuality:
    """Quality assessment for a single field."""

    field: str
    present: bool
    parseable: bool
    raw_value: str = ""
    error: Optional[str] = None


@dataclass
class QualityReport:
    """Overall quality assessment of a deterministic extraction result."""

    fields: Dict[str, FieldQuality] = field(default_factory=dict)
    missing_fields: List[str] = field(default_factory=list)
    invalid_fields: List[str] = field(default_factory=list)
    arithmetic_inconsistent: bool = False
    arithmetic_detail: str = ""
    sufficient: bool = False
    reasons: List[str] = field(default_factory=list)

    @property
    def needs_llm(self) -> bool:
        """Whether LLM fallback should be attempted."""
        return not self.sufficient


def _is_junk_value(raw_value: str) -> bool:
    """Check if a raw value is a junk/placeholder value."""
    return raw_value.strip() in JUNK_VALUES


def _check_field_quality(field_name: str, raw_value: str) -> FieldQuality:
    """Check the quality of a single field value.

    A field is:
    - present: if it exists in the output with a non-junk value.
    - parseable: if the value has a recognizable format for that field type.

    Note: The quality gate checks FORMAT parseability, not full validation.
    For example, an NIF that has the right format (letter + 7 digits + check)
    is "parseable" even if the check digit is wrong — that's the
    normalization/validation layer's job.
    """
    if _is_junk_value(raw_value):
        return FieldQuality(
            field=field_name,
            present=False,
            parseable=False,
            raw_value=raw_value,
            error="Junk value",
        )

    # Passthrough fields: present and non-empty = parseable.
    if field_name in PASSTHROUGH_FIELDS:
        return FieldQuality(
            field=field_name,
            present=True,
            parseable=True,
            raw_value=raw_value,
        )

    # NIF/CIF: check format only (not check-digit validation).
    if field_name == "supplier_nif":
        return _check_nif_format(raw_value)

    # Currency: check if it's a recognizable 3-letter code or symbol.
    if field_name == "currency":
        return _check_currency_format(raw_value)

    # Normalized fields: try the normalizer.
    if field_name in FIELD_NORMALIZERS:
        result = normalize_field(field_name, raw_value)
        return FieldQuality(
            field=field_name,
            present=True,
            parseable=result.success,
            raw_value=raw_value,
            error=result.error if not result.success else None,
        )

    # Unknown field: assume parseable if non-empty.
    return FieldQuality(
        field=field_name,
        present=True,
        parseable=True,
        raw_value=raw_value,
    )


def _check_nif_format(raw_value: str) -> FieldQuality:
    """Check NIF/CIF format (not check-digit validation).

    Accepts:
    - DNI: 8 digits + letter (e.g., 12345678A)
    - NIE: X/Y/Z + 7 digits + letter
    - CIF: letter + 7 digits + letter/digit
    """
    import re

    cleaned = raw_value.strip().upper()

    # DNI format.
    if re.match(r"^\d{8}[A-Z]$", cleaned):
        return FieldQuality(
            field="supplier_nif", present=True, parseable=True,
            raw_value=raw_value,
        )

    # NIE format.
    if re.match(r"^[XYZ]\d{7}[A-Z]$", cleaned):
        return FieldQuality(
            field="supplier_nif", present=True, parseable=True,
            raw_value=raw_value,
        )

    # CIF format.
    if re.match(r"^[A-Z]\d{7}[A-Z0-9]$", cleaned):
        return FieldQuality(
            field="supplier_nif", present=True, parseable=True,
            raw_value=raw_value,
        )

    return FieldQuality(
        field="supplier_nif",
        present=True,
        parseable=False,
        raw_value=raw_value,
        error=f"Unrecognized NIF/CIF format: {raw_value!r}",
    )


def _check_currency_format(raw_value: str) -> FieldQuality:
    """Check if currency value is a recognizable code or symbol."""
    import re

    cleaned = raw_value.strip().upper()

    # ISO-4217 3-letter code.
    if re.match(r"^[A-Z]{3}$", cleaned):
        return FieldQuality(
            field="currency", present=True, parseable=True,
            raw_value=raw_value,
        )

    # Common symbols.
    if cleaned in ("€", "$", "£"):
        return FieldQuality(
            field="currency", present=True, parseable=True,
            raw_value=raw_value,
        )

    # Common names.
    if cleaned in ("EURO", "DOLAR", "DÓLAR", "LIBRA"):
        return FieldQuality(
            field="currency", present=True, parseable=True,
            raw_value=raw_value,
        )

    return FieldQuality(
        field="currency",
        present=True,
        parseable=False,
        raw_value=raw_value,
        error=f"Unrecognized currency: {raw_value!r}",
    )


def _check_arithmetic_consistency(
    total_raw: str, base_raw: str, vat_raw: str
) -> tuple:
    """Check arithmetic consistency: total ≈ base + vat.

    Returns (is_consistent, detail_message).
    Only meaningful when all three values are parseable.
    Tolerance: 0.02 (allows for rounding differences).
    """
    try:
        total = Decimal(total_raw.replace(",", "."))
        base = Decimal(base_raw.replace(",", "."))
        vat = Decimal(vat_raw.replace(",", "."))
    except (InvalidOperation, ValueError):
        return True, ""  # Can't check if values aren't numeric.

    expected = base + vat
    diff = abs(total - expected)
    if diff > Decimal("0.02"):
        return False, (
            f"total ({total}) != base ({base}) + vat ({vat}) = {expected}, "
            f"diff={diff}"
        )
    return True, ""


def evaluate_extraction_quality(
    raw_output: Dict[str, Any],
) -> QualityReport:
    """Evaluate the quality of a deterministic extraction result.

    Args:
        raw_output: The raw extraction output dict (field -> {raw_value, confidence, provenance}).

    Returns:
        QualityReport with detailed assessment.
    """
    report = QualityReport()

    # Evaluate each field in the output.
    for field_name in VALID_FIELDS:
        if field_name not in raw_output:
            # Field is absent.
            report.fields[field_name] = FieldQuality(
                field=field_name, present=False, parseable=False
            )
            report.missing_fields.append(field_name)
            continue

        value = raw_output[field_name]
        if not isinstance(value, dict):
            report.fields[field_name] = FieldQuality(
                field=field_name, present=False, parseable=False,
                error="Value is not a dict",
            )
            report.invalid_fields.append(field_name)
            continue

        raw_value = value.get("raw_value", "")
        if not isinstance(raw_value, str):
            report.fields[field_name] = FieldQuality(
                field=field_name, present=False, parseable=False,
                error="raw_value is not a string",
            )
            report.invalid_fields.append(field_name)
            continue

        fq = _check_field_quality(field_name, raw_value)
        report.fields[field_name] = fq

        if not fq.present:
            report.missing_fields.append(field_name)
        elif not fq.parseable:
            report.invalid_fields.append(field_name)

    # Arithmetic consistency check.
    total_fq = report.fields.get("total_amount")
    base_fq = report.fields.get("base_amount")
    vat_fq = report.fields.get("vat_amount")

    if (
        total_fq and total_fq.present and total_fq.parseable
        and base_fq and base_fq.present and base_fq.parseable
        and vat_fq and vat_fq.present and vat_fq.parseable
    ):
        consistent, detail = _check_arithmetic_consistency(
            total_fq.raw_value, base_fq.raw_value, vat_fq.raw_value
        )
        if not consistent:
            report.arithmetic_inconsistent = True
            report.arithmetic_detail = detail

    # Determine sufficiency.
    # A result is sufficient if:
    # 1. All REQUIRED_FIELDS are present and parseable.
    # 2. No relevant field is missing (absent or junk).
    #    Relevant fields are those needed for expense creation.
    #    Purely optional metadata (payment_method, description) is excluded.
    # 3. No PRESENT relevant field has an unparseable value.
    # 4. No arithmetic inconsistency.

    RELEVANT_FOR_EXPENSE = [
        "supplier_name", "supplier_nif", "invoice_number", "invoice_date",
        "total_amount", "base_amount", "vat_rate", "vat_amount", "currency",
    ]

    # Check required fields: must be present AND parseable.
    for req in REQUIRED_FIELDS:
        fq = report.fields.get(req)
        if fq is None or not fq.present or not fq.parseable:
            report.reasons.append(f"Required field '{req}' is missing or invalid")

    # Check relevant fields: missing OR unparseable → reason to invoke LLM.
    for rel in RELEVANT_FOR_EXPENSE:
        fq = report.fields.get(rel)
        if fq is None or not fq.present:
            report.reasons.append(f"Relevant field '{rel}' is missing")
        elif not fq.parseable:
            report.reasons.append(
                f"Field '{rel}' has unparseable value: {fq.raw_value!r}"
            )

    # Arithmetic.
    if report.arithmetic_inconsistent:
        report.reasons.append(f"Arithmetic inconsistency: {report.arithmetic_detail}")

    report.sufficient = len(report.reasons) == 0

    return report


def should_invoke_llm(
    raw_output: Dict[str, Any],
    llm_configured: bool,
) -> tuple:
    """Determine if LLM fallback should be invoked.

    Returns:
        (should_invoke: bool, report: QualityReport, fields_to_extract: List[str])

    The LLM is invoked when:
    - LLM is configured and enabled.
    - The quality gate reports the result as insufficient.
    - There is at least 1 field to extract (missing or invalid).

    When invoked, the LLM receives the FULL set of fields to extract
    (not just missing ones), so it can provide a complete picture.
    The reconciliation step will preserve deterministic values that are
    valid and high-confidence.
    """
    report = evaluate_extraction_quality(raw_output)

    if not llm_configured:
        return False, report, []

    if report.sufficient:
        return False, report, []

    # Determine which fields to ask the LLM for.
    # We ask for ALL relevant fields (not just missing) so the LLM can
    # provide a complete extraction. Reconciliation will pick the best.
    fields_to_extract: List[str] = []
    for field_name in VALID_FIELDS:
        fq = report.fields.get(field_name)
        if fq is None or not fq.present or not fq.parseable:
            fields_to_extract.append(field_name)

    # If nothing to extract, don't invoke.
    if not fields_to_extract:
        return False, report, []

    return True, report, fields_to_extract
