"""Tests for the extraction quality gate and LLM reconciliation.

Covers:
- Complete valid deterministic result → NO LLM.
- Missing fields → LLM invoked.
- Field present but unparseable (e.g., vat_amount=".") → LLM invoked.
- Arithmetic inconsistency → LLM invoked.
- Mix of valid + invalid deterministic fields.
- Reconciliation preserves valid deterministic values.
- LLM partial/invalid response.
- LLM timeout/error.
- Post-LLM deterministic validation still applies.
- XML/Facturae regression (high-confidence XML results never trigger LLM).
"""
from __future__ import annotations

import json
from typing import Any, Dict
from unittest.mock import patch, MagicMock

import pytest

from backend.services.extraction_quality import (
    QualityReport,
    evaluate_extraction_quality,
    should_invoke_llm,
    _check_field_quality,
    _check_arithmetic_consistency,
    JUNK_VALUES,
)
from backend.services.llm_extraction import (
    LLMExtractionResult,
    extract_with_llm,
    merge_llm_results,
    is_llm_configured,
)
from backend.services.extraction_schema import REQUIRED_FIELDS, VALID_FIELDS


# --- Helpers ---


def _make_field(raw_value: str, confidence: float = 0.8, method: str = "pdf_text_rules") -> Dict[str, Any]:
    """Helper to build a valid field extraction dict."""
    return {
        "raw_value": raw_value,
        "confidence": confidence,
        "provenance": {"method": method, "rule": "test"},
    }


def _complete_valid_output() -> Dict[str, Any]:
    """A complete, valid regex extraction output (all fields parseable)."""
    return {
        "supplier_name": _make_field("Acme Corp"),
        "supplier_nif": _make_field("A12345678"),
        "invoice_number": _make_field("INV-001"),
        "invoice_date": _make_field("2024-01-15"),
        "total_amount": _make_field("121.00"),
        "base_amount": _make_field("100.00"),
        "vat_rate": _make_field("21"),
        "vat_amount": _make_field("21.00"),
        "currency": _make_field("EUR"),
    }


def _partial_output() -> Dict[str, Any]:
    """Partial output: missing several fields."""
    return {
        "supplier_name": _make_field("Acme Corp"),
        "total_amount": _make_field("121.00"),
        "currency": _make_field("EUR"),
    }


def _junk_value_output() -> Dict[str, Any]:
    """Output with a junk value (vat_amount='.')."""
    return {
        "supplier_name": _make_field("Acme Corp"),
        "supplier_nif": _make_field("A12345678"),
        "invoice_number": _make_field("INV-001"),
        "invoice_date": _make_field("2024-01-15"),
        "total_amount": _make_field("147.96"),
        "base_amount": _make_field("147.96"),
        "vat_rate": _make_field("0"),
        "vat_amount": _make_field("."),  # Junk!
        "currency": _make_field("EUR"),
    }


def _arithmetic_inconsistent_output() -> Dict[str, Any]:
    """Output where total != base + vat."""
    return {
        "supplier_name": _make_field("Acme Corp"),
        "supplier_nif": _make_field("A12345678"),
        "invoice_number": _make_field("INV-001"),
        "invoice_date": _make_field("2024-01-15"),
        "total_amount": _make_field("200.00"),
        "base_amount": _make_field("100.00"),
        "vat_rate": _make_field("21"),
        "vat_amount": _make_field("21.00"),  # 100 + 21 = 121 != 200
        "currency": _make_field("EUR"),
    }


def _xml_high_confidence_output() -> Dict[str, Any]:
    """Simulates a complete XML/Facturae extraction (high confidence)."""
    return {
        "supplier_name": _make_field("Acme Corp", 0.98, "xml_schema"),
        "supplier_nif": _make_field("A12345678", 0.98, "xml_schema"),
        "invoice_number": _make_field("FAC-2024-001", 0.97, "xml_schema"),
        "invoice_date": _make_field("2024-01-15", 0.97, "xml_schema"),
        "total_amount": _make_field("121.00", 0.99, "xml_schema"),
        "base_amount": _make_field("100.00", 0.97, "xml_schema"),
        "vat_rate": _make_field("21", 0.95, "xml_schema"),
        "vat_amount": _make_field("21.00", 0.95, "xml_schema"),
        "currency": _make_field("EUR", 0.95, "xml_schema"),
    }


# --- Fixtures ---


@pytest.fixture
def llm_settings(monkeypatch):
    """Configure LLM settings for tests."""
    monkeypatch.setenv("GASTOSE_LLM_ENABLED", "true")
    monkeypatch.setenv("GASTOSE_LLM_ENDPOINT", "http://localhost:4000/v1")
    monkeypatch.setenv("GASTOSE_LLM_MODEL", "test-model")
    monkeypatch.setenv("GASTOSE_LLM_API_KEY", "test-key")
    monkeypatch.setenv("GASTOSE_LLM_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("GASTOSE_LLM_MAX_RETRIES", "1")
    yield


@pytest.fixture
def llm_disabled(monkeypatch):
    """Disable LLM for tests."""
    monkeypatch.setenv("GASTOSE_LLM_ENABLED", "false")
    yield


# --- Tests: evaluate_extraction_quality ---


class TestEvaluateExtractionQuality:
    def test_complete_valid_output_sufficient(self):
        """Complete valid output → sufficient, no LLM needed."""
        report = evaluate_extraction_quality(_complete_valid_output())
        assert report.sufficient is True
        assert report.needs_llm is False
        # Only purely optional metadata may be missing (payment_method, description).
        # No relevant fields should be missing.
        relevant_missing = [
            f for f in report.missing_fields
            if f in ("supplier_name", "supplier_nif", "invoice_number",
                     "invoice_date", "total_amount", "base_amount",
                     "vat_rate", "vat_amount", "currency")
        ]
        assert relevant_missing == []
        assert report.invalid_fields == []
        assert report.arithmetic_inconsistent is False

    def test_partial_output_not_sufficient(self):
        """Missing fields → not sufficient."""
        report = evaluate_extraction_quality(_partial_output())
        assert report.sufficient is False
        assert report.needs_llm is True
        # Missing fields should include the absent ones.
        assert "invoice_date" in report.missing_fields
        assert "base_amount" in report.missing_fields
        assert "vat_rate" in report.missing_fields
        assert "vat_amount" in report.missing_fields

    def test_junk_value_not_sufficient(self):
        """Junk value (vat_amount='.') → not sufficient."""
        report = evaluate_extraction_quality(_junk_value_output())
        assert report.sufficient is False
        assert report.needs_llm is True
        # vat_amount should be flagged as missing (junk = not present).
        assert "vat_amount" in report.missing_fields

    def test_arithmetic_inconsistency_not_sufficient(self):
        """Arithmetic inconsistency → not sufficient."""
        report = evaluate_extraction_quality(_arithmetic_inconsistent_output())
        assert report.sufficient is False
        assert report.needs_llm is True
        assert report.arithmetic_inconsistent is True
        assert "Arithmetic" in report.reasons[0] or "arithmetic" in report.reasons[0].lower()

    def test_xml_high_confidence_sufficient(self):
        """XML/Facturae high-confidence output → sufficient (regression)."""
        report = evaluate_extraction_quality(_xml_high_confidence_output())
        assert report.sufficient is True
        assert report.needs_llm is False

    def test_unparseable_date_not_sufficient(self):
        """Unparseable date → not sufficient."""
        output = _complete_valid_output()
        output["invoice_date"] = _make_field("not-a-date")
        report = evaluate_extraction_quality(output)
        assert report.sufficient is False
        assert "invoice_date" in report.invalid_fields

    def test_unparseable_amount_not_sufficient(self):
        """Unparseable amount → not sufficient."""
        output = _complete_valid_output()
        output["total_amount"] = _make_field("abc")
        report = evaluate_extraction_quality(output)
        assert report.sufficient is False
        assert "total_amount" in report.invalid_fields

    def test_required_field_missing_not_sufficient(self):
        """Missing required field (supplier_name) → not sufficient."""
        output = _complete_valid_output()
        del output["supplier_name"]
        report = evaluate_extraction_quality(output)
        assert report.sufficient is False
        assert "supplier_name" in report.missing_fields

    def test_required_field_junk_not_sufficient(self):
        """Required field with junk value → not sufficient."""
        output = _complete_valid_output()
        output["total_amount"] = _make_field(".")
        report = evaluate_extraction_quality(output)
        assert report.sufficient is False
        assert "total_amount" in report.missing_fields

    def test_mixed_valid_and_invalid_fields(self):
        """Mix of valid and invalid fields → not sufficient, lists both."""
        output = {
            "supplier_name": _make_field("Acme Corp"),
            "total_amount": _make_field("121.00"),
            "currency": _make_field("EUR"),
            "invoice_date": _make_field("invalid-date"),  # Unparseable
            "vat_amount": _make_field("."),  # Junk
        }
        report = evaluate_extraction_quality(output)
        assert report.sufficient is False
        assert "invoice_date" in report.invalid_fields
        assert "vat_amount" in report.missing_fields
        # Valid fields are not flagged.
        assert "supplier_name" not in report.invalid_fields
        assert "total_amount" not in report.invalid_fields


# --- Tests: should_invoke_llm ---


class TestShouldInvokeLLM:
    def test_complete_valid_no_llm(self, llm_settings):
        """Complete valid output → LLM NOT invoked."""
        invoke, report, fields = should_invoke_llm(
            _complete_valid_output(), llm_configured=True
        )
        assert invoke is False
        assert report.sufficient is True
        assert fields == []

    def test_partial_output_invoke_llm(self, llm_settings):
        """Partial output → LLM invoked with missing fields."""
        invoke, report, fields = should_invoke_llm(
            _partial_output(), llm_configured=True
        )
        assert invoke is True
        assert report.sufficient is False
        # Fields to extract should include the missing ones.
        assert "invoice_date" in fields
        assert "base_amount" in fields
        assert "vat_rate" in fields
        assert "vat_amount" in fields

    def test_junk_value_invoke_llm(self, llm_settings):
        """Junk value → LLM invoked."""
        invoke, report, fields = should_invoke_llm(
            _junk_value_output(), llm_configured=True
        )
        assert invoke is True
        assert "vat_amount" in fields

    def test_arithmetic_inconsistency_invoke_llm(self, llm_settings):
        """Arithmetic inconsistency → LLM invoked."""
        invoke, report, fields = should_invoke_llm(
            _arithmetic_inconsistent_output(), llm_configured=True
        )
        assert invoke is True
        assert report.arithmetic_inconsistent is True

    def test_llm_not_configured_no_invoke(self, llm_settings):
        """LLM not configured → never invoked."""
        invoke, report, fields = should_invoke_llm(
            _partial_output(), llm_configured=False
        )
        assert invoke is False
        assert fields == []

    def test_llm_disabled_no_invoke(self, llm_disabled):
        """LLM disabled → never invoked."""
        invoke, report, fields = should_invoke_llm(
            _partial_output(), llm_configured=False
        )
        assert invoke is False

    def test_xml_output_no_llm(self, llm_settings):
        """XML high-confidence output → LLM NOT invoked (regression)."""
        invoke, report, fields = should_invoke_llm(
            _xml_high_confidence_output(), llm_configured=True
        )
        assert invoke is False
        assert report.sufficient is True

    def test_fields_to_extract_excludes_valid_fields(self, llm_settings):
        """Fields to extract should only include missing/invalid ones."""
        output = {
            "supplier_name": _make_field("Acme Corp"),
            "total_amount": _make_field("121.00"),
            "currency": _make_field("EUR"),
            "invoice_date": _make_field("."),  # Junk
        }
        invoke, report, fields = should_invoke_llm(output, llm_configured=True)
        assert invoke is True
        # Valid fields should NOT be in the extraction list.
        assert "supplier_name" not in fields
        assert "total_amount" not in fields
        assert "currency" not in fields
        # Invalid/missing fields SHOULD be in the list.
        assert "invoice_date" in fields


# --- Tests: _check_field_quality ---


class TestCheckFieldQuality:
    def test_valid_amount(self):
        fq = _check_field_quality("total_amount", "121.00")
        assert fq.present is True
        assert fq.parseable is True

    def test_junk_amount(self):
        fq = _check_field_quality("total_amount", ".")
        assert fq.present is False
        assert fq.parseable is False

    def test_unparseable_amount(self):
        fq = _check_field_quality("total_amount", "abc")
        assert fq.present is True
        assert fq.parseable is False

    def test_valid_date(self):
        fq = _check_field_quality("invoice_date", "2024-01-15")
        assert fq.present is True
        assert fq.parseable is True

    def test_es_format_date(self):
        fq = _check_field_quality("invoice_date", "15/01/2024")
        assert fq.present is True
        assert fq.parseable is True

    def test_invalid_date(self):
        fq = _check_field_quality("invoice_date", "not-a-date")
        assert fq.present is True
        assert fq.parseable is False

    def test_valid_vat_rate(self):
        fq = _check_field_quality("vat_rate", "21")
        assert fq.present is True
        assert fq.parseable is True

    def test_zero_vat_rate(self):
        fq = _check_field_quality("vat_rate", "0")
        assert fq.present is True
        assert fq.parseable is True

    def test_unknown_vat_rate(self):
        fq = _check_field_quality("vat_rate", "99")
        assert fq.present is True
        assert fq.parseable is False  # 99 is not a known Spanish VAT rate

    def test_passthrough_field(self):
        fq = _check_field_quality("supplier_name", "Acme Corp")
        assert fq.present is True
        assert fq.parseable is True

    def test_passthrough_empty(self):
        fq = _check_field_quality("supplier_name", "")
        assert fq.present is False
        assert fq.parseable is False

    def test_valid_currency(self):
        fq = _check_field_quality("currency", "EUR")
        assert fq.present is True
        assert fq.parseable is True

    def test_invalid_currency(self):
        fq = _check_field_quality("currency", "XYZ123")
        assert fq.present is True
        assert fq.parseable is False


# --- Tests: _check_arithmetic_consistency ---


class TestArithmeticConsistency:
    def test_consistent(self):
        consistent, detail = _check_arithmetic_consistency("121.00", "100.00", "21.00")
        assert consistent is True
        assert detail == ""

    def test_inconsistent(self):
        consistent, detail = _check_arithmetic_consistency("200.00", "100.00", "21.00")
        assert consistent is False
        assert "200" in detail

    def test_zero_vat_consistent(self):
        """When VAT=0, base should equal total."""
        consistent, detail = _check_arithmetic_consistency("147.96", "147.96", "0.00")
        assert consistent is True

    def test_comma_decimal(self):
        """European format with comma decimal."""
        consistent, detail = _check_arithmetic_consistency("121,00", "100,00", "21,00")
        assert consistent is True

    def test_tolerance(self):
        """Small rounding difference (0.01) is within tolerance."""
        consistent, detail = _check_arithmetic_consistency("121.01", "100.00", "21.00")
        assert consistent is True

    def test_non_numeric(self):
        """Non-numeric values: skip check (return consistent)."""
        consistent, detail = _check_arithmetic_consistency("abc", "def", "ghi")
        assert consistent is True  # Can't check, so no inconsistency.


# --- Tests: merge_llm_results (reconciliation) ---


class TestMergeLLMResultsReconciliation:
    def test_preserves_valid_deterministic_values(self):
        """Valid deterministic values are NOT overridden by LLM."""
        raw_output = {
            "supplier_name": _make_field("Acme Corp", 0.85, "pdf_text_rules"),
            "total_amount": _make_field("121.00", 0.80, "pdf_text_rules"),
            "invoice_date": _make_field("2024-01-15", 0.75, "pdf_text_rules"),
        }
        llm_result = LLMExtractionResult(
            fields={
                "supplier_name": "Acme Corporation",  # Different but deterministic is valid
                "total_amount": "999.99",  # Different but deterministic is valid
                "invoice_date": "2024-06-01",  # Different but deterministic is valid
            },
            model="test-model",
            success=True,
        )

        merged = merge_llm_results(raw_output, llm_result)

        # All deterministic values preserved.
        assert merged["supplier_name"]["raw_value"] == "Acme Corp"
        assert merged["supplier_name"]["provenance"]["method"] == "pdf_text_rules"
        assert merged["total_amount"]["raw_value"] == "121.00"
        assert merged["invoice_date"]["raw_value"] == "2024-01-15"

    def test_replaces_junk_values_with_llm(self):
        """Junk deterministic values ARE replaced by LLM."""
        raw_output = {
            "supplier_name": _make_field("Acme Corp"),
            "total_amount": _make_field("121.00"),
            "vat_amount": _make_field("."),  # Junk
            "invoice_date": _make_field("not-a-date"),  # Unparseable
        }
        llm_result = LLMExtractionResult(
            fields={
                "vat_amount": "21.00",
                "invoice_date": "2024-01-15",
            },
            model="test-model",
            success=True,
        )

        merged = merge_llm_results(raw_output, llm_result)

        # Junk/unparseable values replaced.
        assert merged["vat_amount"]["raw_value"] == "21.00"
        assert merged["vat_amount"]["provenance"]["method"] == "llm_fallback"
        assert merged["invoice_date"]["raw_value"] == "2024-01-15"
        assert merged["invoice_date"]["provenance"]["method"] == "llm_fallback"
        # Valid values preserved.
        assert merged["supplier_name"]["raw_value"] == "Acme Corp"
        assert merged["total_amount"]["raw_value"] == "121.00"

    def test_adds_missing_fields(self):
        """Missing fields are added from LLM."""
        raw_output = {
            "supplier_name": _make_field("Acme Corp"),
            "total_amount": _make_field("121.00"),
        }
        llm_result = LLMExtractionResult(
            fields={
                "invoice_date": "2024-01-15",
                "currency": "EUR",
                "base_amount": "100.00",
            },
            model="test-model",
            success=True,
        )

        merged = merge_llm_results(raw_output, llm_result)

        assert merged["invoice_date"]["raw_value"] == "2024-01-15"
        assert merged["invoice_date"]["confidence"] == 0.55
        assert merged["invoice_date"]["provenance"]["method"] == "llm_fallback"
        assert merged["currency"]["raw_value"] == "EUR"
        assert merged["base_amount"]["raw_value"] == "100.00"

    def test_failed_llm_no_merge(self):
        """Failed LLM result: no changes to raw_output."""
        raw_output = {
            "supplier_name": _make_field("Acme Corp"),
            "total_amount": _make_field("121.00"),
        }
        llm_result = LLMExtractionResult(
            fields={},
            model="test-model",
            success=False,
            error="Timeout",
        )

        merged = merge_llm_results(raw_output, llm_result)
        assert "invoice_date" not in merged
        assert merged["supplier_name"]["raw_value"] == "Acme Corp"

    def test_llm_provenance_distinct(self):
        """LLM fields have distinct provenance."""
        raw_output = {
            "supplier_name": _make_field("Acme Corp"),
        }
        llm_result = LLMExtractionResult(
            fields={"currency": "EUR"},
            model="gpt-4",
            success=True,
        )

        merged = merge_llm_results(raw_output, llm_result)
        assert merged["currency"]["provenance"]["method"] == "llm_fallback"
        assert merged["currency"]["provenance"]["model"] == "gpt-4"
        assert merged["currency"]["provenance"]["source"] == "llm"
        assert merged["currency"]["confidence"] == 0.55


# --- Tests: LLM integration (mocked HTTP) ---


class TestLLMIntegrationWithQualityGate:
    def _mock_httpx_client(self, mock_client_cls, response_body, status_code=200):
        """Helper to configure httpx.Client mock."""
        mock_response = MagicMock()
        mock_response.status_code = status_code
        mock_response.text = json.dumps(response_body) if isinstance(response_body, dict) else str(response_body)
        mock_response.json = MagicMock(return_value=response_body)
        mock_response.raise_for_status = MagicMock()
        if status_code >= 400:
            import httpx
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                f"HTTP {status_code}",
                request=MagicMock(),
                response=mock_response,
            )
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client
        return mock_client

    @patch("backend.services.llm_extraction.httpx.Client")
    def test_llm_fills_junk_field(self, mock_client_cls, llm_settings):
        """Quality gate detects junk vat_amount, LLM fills it."""
        raw_output = _junk_value_output()

        # Quality gate should identify vat_amount as needing LLM.
        invoke, report, fields = should_invoke_llm(raw_output, llm_configured=True)
        assert invoke is True
        assert "vat_amount" in fields

        # Mock LLM response.
        llm_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "vat_amount": "0.00",
                        })
                    }
                }
            ]
        }
        self._mock_httpx_client(mock_client_cls, llm_response)

        result = extract_with_llm("Invoice text...", fields)
        assert result.success is True
        assert result.fields.get("vat_amount") == "0.00"

        # Merge: junk value replaced.
        merged = merge_llm_results(raw_output, result)
        assert merged["vat_amount"]["raw_value"] == "0.00"
        assert merged["vat_amount"]["provenance"]["method"] == "llm_fallback"
        # Other valid fields preserved.
        assert merged["total_amount"]["raw_value"] == "147.96"
        assert merged["total_amount"]["provenance"]["method"] == "pdf_text_rules"

    @patch("backend.services.llm_extraction.httpx.Client")
    def test_llm_timeout_pipeline_continues(self, mock_client_cls, llm_settings):
        """LLM timeout: pipeline continues with deterministic result."""
        import httpx
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.TimeoutException("timed out")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        raw_output = _partial_output()
        invoke, report, fields = should_invoke_llm(raw_output, llm_configured=True)
        assert invoke is True

        result = extract_with_llm("Invoice text...", fields)
        assert result.success is False
        assert "timeout" in result.error.lower()

        # Merge with failed result: no changes.
        merged = merge_llm_results(raw_output, result)
        assert merged == raw_output

    @patch("backend.services.llm_extraction.httpx.Client")
    def test_llm_partial_response(self, mock_client_cls, llm_settings):
        """LLM returns only some fields: partial merge."""
        raw_output = _partial_output()
        invoke, report, fields = should_invoke_llm(raw_output, llm_configured=True)
        assert invoke is True

        llm_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "invoice_date": "2024-01-15",
                            "base_amount": None,  # Not found
                            "vat_rate": "21",
                            "vat_amount": None,  # Not found
                        })
                    }
                }
            ]
        }
        self._mock_httpx_client(mock_client_cls, llm_response)

        result = extract_with_llm("Invoice text...", fields)
        assert result.success is True
        assert "invoice_date" in result.fields
        assert "vat_rate" in result.fields
        assert "base_amount" not in result.fields
        assert "vat_amount" not in result.fields

        merged = merge_llm_results(raw_output, result)
        assert merged["invoice_date"]["raw_value"] == "2024-01-15"
        assert merged["vat_rate"]["raw_value"] == "21"
        # Missing fields remain absent.
        assert "base_amount" not in merged
        assert "vat_amount" not in merged

    @patch("backend.services.llm_extraction.httpx.Client")
    def test_llm_invalid_json(self, mock_client_cls, llm_settings):
        """LLM returns non-JSON: graceful degradation."""
        raw_output = _partial_output()
        invoke, report, fields = should_invoke_llm(raw_output, llm_configured=True)
        assert invoke is True

        llm_response = {
            "choices": [
                {
                    "message": {
                        "content": "I cannot extract the fields."
                    }
                }
            ]
        }
        self._mock_httpx_client(mock_client_cls, llm_response)

        result = extract_with_llm("Invoice text...", fields)
        assert result.success is False

        merged = merge_llm_results(raw_output, result)
        assert merged == raw_output


# --- Tests: Post-LLM validation still applies ---


class TestPostLLMValidation:
    def test_llm_value_still_validated_by_schema(self):
        """After LLM merge, the result still goes through schema validation."""
        from backend.services.extraction_schema import validate_extraction_output

        raw_output = _partial_output()
        llm_result = LLMExtractionResult(
            fields={
                "invoice_date": "2024-01-15",
                "base_amount": "100.00",
                "vat_rate": "21",
                "vat_amount": "21.00",
            },
            model="test-model",
            success=True,
        )
        merged = merge_llm_results(raw_output, llm_result)

        # Schema validation should pass (all required fields present).
        result = validate_extraction_output(merged, "pdf_text_rules")
        assert result.is_valid is True
        assert len(result.fields) >= 5  # At least the merged fields.

    def test_llm_invalid_value_caught_by_normalization(self):
        """If LLM returns an unparseable value, normalization catches it."""
        from backend.services.normalization_service import normalize_field

        # Simulate LLM returning a bad amount.
        llm_value = "not-a-number"
        result = normalize_field("total_amount", llm_value)
        assert result.success is False
        assert result.error is not None

    def test_llm_value_passes_normalization(self):
        """Valid LLM value passes normalization."""
        from backend.services.normalization_service import normalize_field

        result = normalize_field("total_amount", "121.00")
        assert result.success is True
        assert result.normalized_value == "121.00"

        result = normalize_field("invoice_date", "2024-01-15")
        assert result.success is True
        assert result.normalized_value == "2024-01-15"


# --- Tests: XML/Facturae regression ---


class TestXMLRegression:
    def test_xml_complete_no_llm(self, llm_settings):
        """Complete XML extraction never triggers LLM."""
        invoke, report, fields = should_invoke_llm(
            _xml_high_confidence_output(), llm_configured=True
        )
        assert invoke is False
        assert report.sufficient is True
        assert fields == []

    def test_xml_partial_triggers_llm(self, llm_settings):
        """If XML extraction is somehow partial, LLM can fill gaps."""
        xml_output = _xml_high_confidence_output()
        del xml_output["vat_amount"]  # Simulate missing field.
        del xml_output["base_amount"]

        invoke, report, fields = should_invoke_llm(xml_output, llm_configured=True)
        assert invoke is True
        assert "vat_amount" in fields
        assert "base_amount" in fields
        # Valid XML fields are NOT re-extracted.
        assert "supplier_name" not in fields
        assert "total_amount" not in fields

    def test_xml_arithmetic_consistent(self, llm_settings):
        """XML with consistent arithmetic → no LLM."""
        invoke, report, fields = should_invoke_llm(
            _xml_high_confidence_output(), llm_configured=True
        )
        assert report.arithmetic_inconsistent is False
        assert invoke is False
