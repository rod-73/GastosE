"""Extraction output schema validation (VR-SCHEMA-1).

Every extraction method must produce output conforming to this strict
schema. If validation fails, the job is marked `failed` and NO partial
values are persisted (per V2-S1 acceptance criteria).

The schema defines the required fields and their types. Each field value
is a dict with:
  - raw_value: str (the extracted value as-is from the source)
  - confidence: float in [0, 1]
  - provenance: dict with at least {method: str}
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Required fields for a valid extraction output.
# These are the minimum fields that must be present for the extraction
# to be considered successful. Missing required fields => validation_error.
REQUIRED_FIELDS: List[str] = [
    "supplier_name",
    "total_amount",
]

# Optional fields (may or may not be present).
OPTIONAL_FIELDS: List[str] = [
    "supplier_nif",
    "invoice_number",
    "invoice_date",
    "base_amount",
    "vat_rate",
    "vat_amount",
    "currency",
    "payment_method",
    "description",
]

# All valid field names.
VALID_FIELDS: List[str] = REQUIRED_FIELDS + OPTIONAL_FIELDS


@dataclass
class FieldExtraction:
    """A single extracted field with confidence and provenance."""

    field: str
    raw_value: str
    confidence: float
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "raw_value": self.raw_value,
            "confidence": self.confidence,
            "provenance": self.provenance,
        }


@dataclass
class ExtractionResult:
    """Validated extraction output."""

    fields: List[FieldExtraction] = field(default_factory=list)
    method: str = ""
    errors: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def get_field(self, name: str) -> Optional[FieldExtraction]:
        for f in self.fields:
            if f.field == name:
                return f
        return None


def validate_extraction_output(
    raw_output: Dict[str, Any],
    method: str,
) -> ExtractionResult:
    """Validate raw extraction output against the strict schema (VR-SCHEMA-1).

    Rules:
    1. Output must be a dict.
    2. Every key must be in VALID_FIELDS.
    3. Every value must be a dict with: raw_value (str), confidence (float 0-1),
       provenance (dict with 'method' key).
    4. All REQUIRED_FIELDS must be present.
    5. No empty raw_value for required fields.

    Returns an ExtractionResult with any validation errors.
    """
    result = ExtractionResult(method=method)

    if not isinstance(raw_output, dict):
        result.errors.append("Output must be a dictionary")
        return result

    # Check for unknown fields.
    for key in raw_output:
        if key not in VALID_FIELDS:
            result.errors.append(f"Unknown field: {key!r}")

    # Validate each field's structure.
    for key, value in raw_output.items():
        if key not in VALID_FIELDS:
            continue  # already reported

        if not isinstance(value, dict):
            result.errors.append(f"Field {key!r}: value must be a dict")
            continue

        # raw_value
        raw_value = value.get("raw_value")
        if raw_value is None:
            result.errors.append(f"Field {key!r}: missing 'raw_value'")
        elif not isinstance(raw_value, str):
            result.errors.append(f"Field {key!r}: 'raw_value' must be a string")
        elif key in REQUIRED_FIELDS and raw_value.strip() == "":
            result.errors.append(f"Field {key!r}: 'raw_value' must not be empty")

        # confidence
        confidence = value.get("confidence")
        if confidence is None:
            result.errors.append(f"Field {key!r}: missing 'confidence'")
        elif not isinstance(confidence, (int, float)):
            result.errors.append(f"Field {key!r}: 'confidence' must be a number")
        elif not (0 <= confidence <= 1):
            result.errors.append(
                f"Field {key!r}: 'confidence' must be in [0, 1]"
            )

        # provenance
        provenance = value.get("provenance")
        if provenance is None:
            result.errors.append(f"Field {key!r}: missing 'provenance'")
        elif not isinstance(provenance, dict):
            result.errors.append(f"Field {key!r}: 'provenance' must be a dict")
        elif "method" not in provenance:
            result.errors.append(
                f"Field {key!r}: 'provenance' must contain 'method'"
            )

    # Check required fields are present.
    for req in REQUIRED_FIELDS:
        if req not in raw_output:
            result.errors.append(f"Missing required field: {req!r}")

    # Build valid fields list.
    for key, value in raw_output.items():
        if key not in VALID_FIELDS:
            continue
        if not isinstance(value, dict):
            continue
        raw_value = value.get("raw_value")
        confidence = value.get("confidence")
        provenance = value.get("provenance")
        if (
            isinstance(raw_value, str)
            and isinstance(confidence, (int, float))
            and 0 <= confidence <= 1
            and isinstance(provenance, dict)
            and "method" in provenance
        ):
            result.fields.append(
                FieldExtraction(
                    field=key,
                    raw_value=raw_value,
                    confidence=float(confidence),
                    provenance=provenance,
                )
            )

    return result
