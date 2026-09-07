"""LLM extraction fallback (ADR-0010: ExtractionLLM provider abstraction).

Provider-neutral abstraction for LLM-based field extraction. The application
does NOT depend on any specific LLM provider. Configuration (endpoint, model,
API key, timeout) is read from Settings (env vars) at runtime.

Deterministic first philosophy:
- LLM is ONLY invoked when deterministic extraction (regex/parser) is incomplete.
- LLM proposes values; deterministic validation (VR-SCHEMA-1) still decides validity.
- LLM output is marked with distinct provenance and lower confidence.
- LLM failure/indisponibility NEVER breaks the pipeline (graceful degradation).

Interface (ADR-0010):
- Input: document text + list of missing fields.
- Output: dict of {field: value} for successfully extracted fields.
- The caller merges results into the raw extraction output and re-validates.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from backend.config import get_settings
from backend.services.extraction_schema import VALID_FIELDS

logger = logging.getLogger(__name__)


# --- Data classes ---


@dataclass
class LLMExtractionResult:
    """Result of an LLM extraction attempt."""

    fields: Dict[str, str] = field(default_factory=dict)
    model: str = ""
    success: bool = False
    error: Optional[str] = None

    @property
    def field_count(self) -> int:
        return len(self.fields)


# --- Prompt ---

EXTRACTION_SYSTEM_PROMPT = (
    "You are an invoice data extraction assistant. "
    "Extract specific fields from the invoice text provided. "
    "Return ONLY a valid JSON object. No markdown, no explanations."
)

EXTRACTION_USER_TEMPLATE = """Extract the following fields from this invoice text.
For each field, return the value as a string. If a field is not present, use null.

Fields to extract:
{fields_list}

Rules:
- Dates: ISO-8601 format (YYYY-MM-DD).
- Amounts: numeric with dot decimal separator (e.g., "25.06").
- VAT rate: numeric percentage (e.g., "21" for 21%).
- If VAT is 0%%, set vat_rate to "0" and vat_amount to "0".
- If base amount is not stated but VAT is 0%%, base_amount equals total_amount.
- Currency: ISO-4217 code (EUR, USD, GBP, etc.).
- Extract values exactly as they appear in the document (do not convert formats).

Return a JSON object with exactly these keys: {json_keys}

Invoice text:
---
{invoice_text}
---
"""

EXTRACTION_USER_TEMPLATE_VISION = """Extract the following fields from this invoice image.
For each field, return the value as a string. If a field is not present, use null.

Fields to extract:
{fields_list}

Rules:
- Dates: ISO-8601 format (YYYY-MM-DD).
- Amounts: numeric with dot decimal separator (e.g., "25.06").
- VAT rate: numeric percentage (e.g., "21" for 21%).
- If VAT is 0%%, set vat_rate to "0" and vat_amount to "0".
- If base amount is not stated but VAT is 0%%, base_amount equals total_amount.
- Currency: ISO-4217 code (EUR, USD, GBP, etc.).
- Extract values exactly as they appear in the document (do not convert formats).

Return a JSON object with exactly these keys: {json_keys}

The invoice is provided as an image attachment.
"""


# --- Core abstraction ---


def is_llm_configured() -> bool:
    """Check if LLM fallback is enabled and configured.

    Returns True only if:
    - LLM_ENABLED is True.
    - LLM_ENDPOINT is non-empty.
    - LLM_MODEL is non-empty.
    """
    settings = get_settings()
    return (
        settings.LLM_ENABLED
        and bool(settings.LLM_ENDPOINT)
        and bool(settings.LLM_MODEL)
    )


def find_missing_fields(regex_result: Dict[str, Any]) -> List[str]:
    """Identify which fields are missing or invalid in regex extraction.

    A field is considered missing/invalid if:
    - It is not present in the result.
    - Its raw_value is empty, ".", "-", "N/A", or "null".

    Only fields in VALID_FIELDS are considered.
    """
    missing: List[str] = []
    for field_name in VALID_FIELDS:
        if field_name not in regex_result:
            missing.append(field_name)
            continue
        value = regex_result[field_name]
        if not isinstance(value, dict):
            missing.append(field_name)
            continue
        raw_value = value.get("raw_value", "")
        if not raw_value or raw_value.strip() in (".", "-", "N/A", "null", ""):
            missing.append(field_name)
    return missing


# Fields that are relevant for expense creation. LLM fallback is only
# triggered when one of these is missing (not purely optional metadata).
RELEVANT_FIELDS: List[str] = [
    "supplier_name",
    "supplier_nif",
    "invoice_number",
    "invoice_date",
    "total_amount",
    "base_amount",
    "vat_rate",
    "vat_amount",
    "currency",
]


def should_use_llm(regex_result: Dict[str, Any]) -> bool:
    """Determine if LLM fallback should be attempted.

    Conditions:
    - LLM is configured and enabled.
    - Regex extraction produced at least 2 valid fields.
    - At least one REQUIRED field is present (basic sanity).
    - At least one RELEVANT field is missing/invalid.
      (Purely optional metadata fields like payment_method, description
      do NOT trigger LLM invocation.)
    """
    if not is_llm_configured():
        return False

    from backend.services.extraction_schema import REQUIRED_FIELDS

    # Must have at least 2 fields extracted by regex.
    valid_fields = [
        k for k, v in regex_result.items()
        if k in VALID_FIELDS and isinstance(v, dict)
        and v.get("raw_value", "").strip() not in ("", ".", "-", "N/A", "null")
    ]
    if len(valid_fields) < 2:
        return False

    # Must have at least one required field present.
    has_required = any(f in valid_fields for f in REQUIRED_FIELDS)
    if not has_required:
        return False

    # Must have at least one RELEVANT field missing.
    missing_relevant = [f for f in RELEVANT_FIELDS if f not in valid_fields]
    return len(missing_relevant) > 0


def extract_with_llm(
    invoice_text: str,
    missing_fields: List[str],
    image_base64: Optional[str] = None,
) -> LLMExtractionResult:
    """Invoke the LLM to extract missing fields from invoice text or image.

    This is the core of the ExtractionLLM abstraction (ADR-0010).
    Provider-neutral: uses OpenAI-compatible chat completions API.

    Args:
        invoice_text: Full text extracted from the document.
        missing_fields: List of field names to extract.
        image_base64: Optional base64-encoded image (for scanned PDFs).
            When provided, the LLM is invoked in vision mode.

    Returns:
        LLMExtractionResult with extracted fields (only valid ones).

    Never raises: all errors are caught and returned in the result.
    """
    settings = get_settings()

    if not missing_fields:
        return LLMExtractionResult(success=True, model=settings.LLM_MODEL)

    # Build prompt.
    fields_list = "\n".join(f"- {f}" for f in missing_fields)
    json_keys = json.dumps(missing_fields)

    if image_base64:
        # Vision mode: send image instead of text.
        user_prompt = EXTRACTION_USER_TEMPLATE_VISION.format(
            fields_list=fields_list,
            json_keys=json_keys,
        )
        # OpenAI-compatible vision message format.
        user_content = [
            {"type": "text", "text": user_prompt},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{image_base64}"
                },
            },
        ]
    else:
        # Text mode.
        user_prompt = EXTRACTION_USER_TEMPLATE.format(
            fields_list=fields_list,
            json_keys=json_keys,
            invoice_text=invoice_text[: settings.LLM_MAX_INPUT_CHARS],
        )
        user_content = user_prompt

    # Build request.
    url = settings.LLM_ENDPOINT.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if settings.LLM_API_KEY:
        headers["Authorization"] = f"Bearer {settings.LLM_API_KEY}"

    payload = {
        "model": settings.LLM_MODEL,
        "messages": [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.1,
        "max_tokens": 500,
    }

    # Execute with retries.
    last_error: Optional[str] = None
    for attempt in range(settings.LLM_MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
                response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            break
        except httpx.TimeoutException:
            last_error = f"Timeout after {settings.LLM_TIMEOUT_SECONDS}s"
            logger.warning(
                "LLM request timeout (attempt %d/%d)",
                attempt + 1,
                settings.LLM_MAX_RETRIES + 1,
            )
        except httpx.ConnectError as e:
            last_error = f"Connection error: {e}"
            logger.warning(
                "LLM connection error (attempt %d/%d): %s",
                attempt + 1,
                settings.LLM_MAX_RETRIES + 1,
                e,
            )
        except httpx.HTTPStatusError as e:
            # 4xx errors are not retryable.
            if 400 <= e.response.status_code < 500:
                last_error = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                logger.error("LLM HTTP error (non-retryable): %s", last_error)
                break
            last_error = f"HTTP {e.response.status_code}"
            logger.warning(
                "LLM HTTP error (attempt %d/%d): %s",
                attempt + 1,
                settings.LLM_MAX_RETRIES + 1,
                last_error,
            )
        except httpx.HTTPError as e:
            last_error = f"Request error: {e}"
            logger.warning(
                "LLM request error (attempt %d/%d): %s",
                attempt + 1,
                settings.LLM_MAX_RETRIES + 1,
                e,
            )
    else:
        # All retries exhausted.
        return LLMExtractionResult(
            success=False,
            model=settings.LLM_MODEL,
            error=last_error or "Max retries exhausted",
        )

    if "response" not in dir() or response is None:
        return LLMExtractionResult(
            success=False,
            model=settings.LLM_MODEL,
            error=last_error or "No response",
        )

    # Parse response.
    try:
        result_json = response.json()
        content = result_json["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        return LLMExtractionResult(
            success=False,
            model=settings.LLM_MODEL,
            error=f"Malformed LLM response: {e}",
        )

    # Extract JSON from response (LLM may wrap in markdown or add text).
    extracted = _parse_llm_json(content, missing_fields)
    if extracted is None:
        return LLMExtractionResult(
            success=False,
            model=settings.LLM_MODEL,
            error="Could not parse JSON from LLM response",
        )

    # Filter: only return fields that were requested and have valid values.
    valid_fields: Dict[str, str] = {}
    for field_name in missing_fields:
        if field_name not in VALID_FIELDS:
            continue
        value = extracted.get(field_name)
        if value is None:
            continue
        value_str = str(value).strip()
        if not value_str or value_str in (".", "-", "N/A", "null"):
            continue
        valid_fields[field_name] = value_str

    return LLMExtractionResult(
        fields=valid_fields,
        model=settings.LLM_MODEL,
        success=True,
    )


# --- Helpers ---


def _parse_llm_json(
    content: str, expected_fields: List[str]
) -> Optional[Dict[str, Any]]:
    """Parse JSON from LLM response content.

    Handles:
    - Pure JSON.
    - JSON wrapped in markdown code blocks.
    - JSON with surrounding text.
    """
    # Try direct parse first.
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # Try to extract JSON object from markdown code block.
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    # Try to find the first JSON object in the content.
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    return None


def merge_llm_results(
    raw_output: Dict[str, Any],
    llm_result: LLMExtractionResult,
) -> Dict[str, Any]:
    """Merge LLM results into the raw extraction output.

    Reconciliation strategy:
    - If the deterministic value is valid (parseable, non-junk): KEEP it.
      The LLM never overrides a valid deterministic value.
    - If the deterministic value is invalid/junk/missing: USE the LLM value.
    - LLM fields get distinct provenance and lower confidence (0.55).
    - Deterministic fields retain their original provenance and confidence.

    This ensures we never lose a good deterministic value while filling
    gaps with LLM output.

    Args:
        raw_output: The existing extraction output (from regex/parser).
        llm_result: The LLM extraction result.

    Returns:
        The updated raw_output dict (modified in place and returned).
    """
    if not llm_result.success or not llm_result.fields:
        return raw_output

    for field_name, value in llm_result.fields.items():
        if field_name not in VALID_FIELDS:
            continue

        # Check if the existing deterministic value is valid.
        if field_name in raw_output:
            existing = raw_output[field_name]
            if isinstance(existing, dict):
                existing_raw = existing.get("raw_value", "")
                if isinstance(existing_raw, str) and existing_raw.strip():
                    # Use the quality gate to check parseability.
                    from backend.services.extraction_quality import (
                        _check_field_quality,
                    )
                    fq = _check_field_quality(field_name, existing_raw)
                    if fq.present and fq.parseable:
                        # Deterministic value is valid: KEEP it.
                        continue

        # Use LLM value (either field was missing, junk, or unparseable).
        raw_output[field_name] = {
            "raw_value": value,
            "confidence": 0.55,  # Lower than regex (0.6-0.85)
            "provenance": {
                "method": "llm_fallback",
                "model": llm_result.model,
                "source": "llm",
            },
        }

    return raw_output
