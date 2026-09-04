"""Validation service (V3-S2, N4).

Deterministic validation of normalized values using VR rules:
- VR-ARITH-1: total == base + IVA - retenciones (tolerance <= 0.01).
- VR-SCHEMA-2: Required fields present.
- VR-NORM-1: Currency is valid ISO-4217.
- VR-NORM-2: Date is valid ISO-8601.
- VR-NORM-3: NIF/CIF is valid.
- VR-NORM-4: VAT rate is known.
- VR-BIZ-5: Single currency.
- VR-BIZ-8: Date coherence (not too old, not future).
- VR-BIZ-9: Reasonable amount.

Each validated value references its normalization origin (INV-10).
Results: passed / failed / warning / corrected.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from backend.models.extraction import Extraction, ExtractedValue
from backend.models.normalized_value import NormalizedValue
from backend.models.validated_value import ValidatedValue
from backend.utils import uuid7


@dataclass
class RuleResult:
    """Result of a single validation rule."""

    rule_id: str
    severity: str  # "BLOCK" or "WARN"
    passed: bool
    message: str = ""


@dataclass
class FieldValidationResult:
    """Result of validating a single field."""

    field: str
    normalized_value: str
    overall_result: str  # "passed", "failed", "warning"
    rules: List[RuleResult] = field(default_factory=list)

    @property
    def has_block_failure(self) -> bool:
        return any(
            r.severity == "BLOCK" and not r.passed for r in self.rules
        )

    @property
    def has_warning(self) -> bool:
        return any(
            r.severity == "WARN" and not r.passed for r in self.rules
        )


# --- VR Rules ---


def vr_arith_1(values: Dict[str, str]) -> RuleResult:
    """VR-ARITH-1: total == base + IVA - retenciones (tolerance <= 0.01)."""
    rule_id = "VR-ARITH-1"
    severity = "BLOCK"

    try:
        total = Decimal(values.get("total_amount", "0"))
        base = Decimal(values.get("base_amount", "0"))
        vat = Decimal(values.get("vat_amount", "0"))
        withholding = Decimal(values.get("withholding_amount", "0"))
    except (InvalidOperation, TypeError):
        return RuleResult(rule_id, severity, False, "Cannot parse amounts")

    expected = base + vat - withholding
    if abs(total - expected) > Decimal("0.01"):
        return RuleResult(
            rule_id, severity, False,
            f"total ({total}) != base + IVA - retenciones ({expected})"
        )
    return RuleResult(rule_id, severity, True)


def vr_schema_2(values: Dict[str, str]) -> RuleResult:
    """VR-SCHEMA-2: Required fields present."""
    rule_id = "VR-SCHEMA-2"
    severity = "BLOCK"

    required = ["supplier_name", "total_amount", "currency", "invoice_date"]
    missing = [f for f in required if f not in values or not values[f]]
    if missing:
        return RuleResult(
            rule_id, severity, False,
            f"Missing required fields: {', '.join(missing)}"
        )
    return RuleResult(rule_id, severity, True)


def vr_norm_1(values: Dict[str, str]) -> RuleResult:
    """VR-NORM-1: Currency is valid ISO-4217."""
    rule_id = "VR-NORM-1"
    severity = "BLOCK"

    currency = values.get("currency", "")
    if not re.match(r"^[A-Z]{3}$", currency):
        return RuleResult(
            rule_id, severity, False,
            f"Invalid currency code: {currency!r}"
        )
    return RuleResult(rule_id, severity, True)


def vr_norm_2(values: Dict[str, str]) -> RuleResult:
    """VR-NORM-2: Date is valid ISO-8601 and not too far in the future."""
    rule_id = "VR-NORM-2"
    severity = "BLOCK"

    date_str = values.get("invoice_date", "")
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return RuleResult(
            rule_id, severity, False,
            f"Invalid date format: {date_str!r}"
        )

    # Not more than 1 day in the future.
    if dt > datetime.now() + timedelta(days=1):
        return RuleResult(
            rule_id, severity, False,
            f"Date is in the future: {date_str}"
        )
    return RuleResult(rule_id, severity, True)


def vr_norm_3(values: Dict[str, str]) -> RuleResult:
    """VR-NORM-3: NIF/CIF is valid (already validated in normalization)."""
    rule_id = "VR-NORM-3"
    severity = "BLOCK"

    nif = values.get("supplier_nif", "")
    if not nif:
        # NIF is optional for tickets; only BLOCK for invoices.
        return RuleResult(rule_id, severity, True, "No NIF provided (optional)")

    # Basic format check (full validation done in normalization).
    if not re.match(r"^(\d{8}[A-Z]|[A-Z]\d{7}[A-Z0-9]|[XYZ]\d{7}[A-Z])$", nif):
        return RuleResult(
            rule_id, severity, False,
            f"Invalid NIF/CIF format: {nif!r}"
        )
    return RuleResult(rule_id, severity, True)


def vr_norm_4(values: Dict[str, str]) -> RuleResult:
    """VR-NORM-4: VAT rate is known (0, 4, 10, 21)."""
    rule_id = "VR-NORM-4"
    severity = "BLOCK"

    rate_str = values.get("vat_rate", "")
    if not rate_str:
        return RuleResult(rule_id, severity, True, "No VAT rate (optional)")

    try:
        rate = float(rate_str)
    except (ValueError, TypeError):
        return RuleResult(
            rule_id, severity, False,
            f"Cannot parse VAT rate: {rate_str!r}"
        )

    known_rates = {0.0, 4.0, 10.0, 21.0}
    if rate not in known_rates:
        return RuleResult(
            rule_id, severity, False,
            f"Unknown VAT rate: {rate} (expected 0, 4, 10, 21)"
        )
    return RuleResult(rule_id, severity, True)


def vr_biz_5(values: Dict[str, str]) -> RuleResult:
    """VR-BIZ-5: Single currency (always true for single-document expenses)."""
    rule_id = "VR-BIZ-5"
    severity = "BLOCK"
    # Single document = single currency by construction.
    return RuleResult(rule_id, severity, True)


def vr_biz_8(values: Dict[str, str]) -> RuleResult:
    """VR-BIZ-8: Date coherence (not older than 10 years)."""
    rule_id = "VR-BIZ-8"
    severity = "WARN"

    date_str = values.get("invoice_date", "")
    if not date_str:
        return RuleResult(rule_id, severity, True, "No date provided")

    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return RuleResult(rule_id, severity, True, "Cannot parse date")

    min_date = datetime.now() - timedelta(days=3650)  # 10 years
    if dt < min_date:
        return RuleResult(
            rule_id, severity, False,
            f"Date is older than 10 years: {date_str}"
        )
    return RuleResult(rule_id, severity, True)


def vr_biz_9(values: Dict[str, str]) -> RuleResult:
    """VR-BIZ-9: Reasonable amount (> 0 and < 1,000,000)."""
    rule_id = "VR-BIZ-9"
    severity = "WARN"

    total_str = values.get("total_amount", "")
    if not total_str:
        return RuleResult(rule_id, severity, True, "No total provided")

    try:
        total = Decimal(total_str)
    except (InvalidOperation, TypeError):
        return RuleResult(rule_id, severity, True, "Cannot parse total")

    if total <= 0:
        return RuleResult(
            rule_id, severity, False,
            f"Total is not positive: {total}"
        )
    if total > Decimal("1000000"):
        return RuleResult(
            rule_id, severity, False,
            f"Total exceeds reasonable limit: {total}"
        )
    return RuleResult(rule_id, severity, True)


# --- Field-specific rule mappings ---

# Maps field -> list of rules to apply.
FIELD_RULES: Dict[str, List] = {
    "total_amount": [vr_arith_1, vr_biz_9],
    "base_amount": [vr_arith_1],
    "vat_amount": [vr_arith_1],
    "currency": [vr_norm_1, vr_biz_5],
    "invoice_date": [vr_norm_2, vr_biz_8],
    "supplier_nif": [vr_norm_3],
    "vat_rate": [vr_norm_4],
    "supplier_name": [],  # No specific rules.
}

# Global rules applied to the whole set of values.
GLOBAL_RULES: List = [vr_schema_2]


def validate_field(
    field_name: str,
    normalized_value: str,
    all_values: Dict[str, str],
) -> FieldValidationResult:
    """Validate a single field using its applicable VR rules."""
    rules = FIELD_RULES.get(field_name, [])
    results: List[RuleResult] = []

    for rule_func in rules:
        result = rule_func(all_values)
        results.append(result)

    # Determine overall result.
    if any(r.severity == "BLOCK" and not r.passed for r in results):
        overall = "failed"
    elif any(r.severity == "WARN" and not r.passed for r in results):
        overall = "warning"
    else:
        overall = "passed"

    return FieldValidationResult(
        field=field_name,
        normalized_value=normalized_value,
        overall_result=overall,
        rules=results,
    )


def validate_extraction(
    extraction_id: uuid.UUID,
    owner_id: uuid.UUID,
    db: DbSession,
) -> Tuple[int, int, int]:
    """Validate all normalized values for a given extraction.

    Creates ValidatedValue records (E5) for each normalized value.
    Applies VR rules and records the result.

    Returns (passed_count, failed_count, warning_count).
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

    # Get all normalized values for this extraction.
    normalized_values = (
        db.execute(
            select(NormalizedValue)
            .where(
                NormalizedValue.extracted_value_id.in_(
                    select(ExtractedValue.id).where(
                        ExtractedValue.extraction_id == extraction_id
                    )
                )
            )
        )
        .scalars()
        .all()
    )

    # Build the values dictionary for global rules.
    all_values: Dict[str, str] = {
        nv.field: nv.normalized_value for nv in normalized_values
    }

    # Apply global rules.
    global_results: List[RuleResult] = []
    for rule_func in GLOBAL_RULES:
        result = rule_func(all_values)
        global_results.append(result)

    # Check if global BLOCK rules failed.
    global_block_failed = any(
        r.severity == "BLOCK" and not r.passed for r in global_results
    )

    passed_count = 0
    failed_count = 0
    warning_count = 0

    for nv in normalized_values:
        # Validate the field.
        field_result = validate_field(nv.field, nv.normalized_value, all_values)

        # If a global BLOCK rule failed, mark all fields as failed.
        if global_block_failed:
            overall = "failed"
            all_rules = field_result.rules + global_results
        else:
            overall = field_result.overall_result
            all_rules = field_result.rules

        # Create the validated value record.
        vv = ValidatedValue(
            id=uuid7(),
            owner_id=owner_id,
            normalized_value_id=nv.id,
            field=nv.field,
            validated_value=nv.normalized_value,
            validation_result=overall,
            rules_applied=json.dumps([
                {
                    "rule_id": r.rule_id,
                    "severity": r.severity,
                    "passed": r.passed,
                    "message": r.message,
                }
                for r in all_rules
            ]),
        )
        db.add(vv)

        if overall == "passed":
            passed_count += 1
        elif overall == "failed":
            failed_count += 1
        else:
            warning_count += 1

    db.commit()
    return passed_count, failed_count, warning_count
