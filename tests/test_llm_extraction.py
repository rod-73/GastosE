"""Tests for LLM extraction fallback (ADR-0010).

Covers:
- LLM fallback successful (partial fields filled).
- LLM response invalid (non-JSON, malformed).
- LLM timeout / connection error (graceful degradation).
- LLM not invoked when regex is complete.
- LLM not invoked when not configured.
- LLM not invoked when regex has too few fields.
- merge_llm_results: only adds missing fields, preserves existing.
- find_missing_fields: correct detection.
- should_use_llm: correct activation logic.
"""
from __future__ import annotations

import json
from typing import Any, Dict
from unittest.mock import patch, MagicMock

import pytest

from backend.services.llm_extraction import (
    LLMExtractionResult,
    extract_with_llm,
    find_missing_fields,
    is_llm_configured,
    merge_llm_results,
    should_use_llm,
    _parse_llm_json,
)
from backend.services.extraction_schema import REQUIRED_FIELDS, VALID_FIELDS


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


@pytest.fixture
def llm_not_configured(monkeypatch):
    """LLM enabled but no endpoint/model."""
    monkeypatch.setenv("GASTOSE_LLM_ENABLED", "true")
    monkeypatch.setenv("GASTOSE_LLM_ENDPOINT", "")
    monkeypatch.setenv("GASTOSE_LLM_MODEL", "")
    yield


def _make_field(raw_value: str, confidence: float = 0.8, method: str = "pdf_text_rules") -> Dict[str, Any]:
    """Helper to build a valid field extraction dict."""
    return {
        "raw_value": raw_value,
        "confidence": confidence,
        "provenance": {"method": method, "rule": "test"},
    }


def _complete_regex_output() -> Dict[str, Any]:
    """A complete regex extraction output (all fields present)."""
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


def _partial_regex_output() -> Dict[str, Any]:
    """A partial regex extraction output (missing some fields)."""
    return {
        "supplier_name": _make_field("Acme Corp"),
        "total_amount": _make_field("121.00"),
        "currency": _make_field("EUR"),
    }


# --- Tests: is_llm_configured ---


class TestIsLLMConfigured:
    def test_configured(self, llm_settings):
        assert is_llm_configured() is True

    def test_disabled(self, llm_disabled):
        assert is_llm_configured() is False

    def test_no_endpoint(self, llm_not_configured):
        assert is_llm_configured() is False


# --- Tests: find_missing_fields ---


class TestFindMissingFields:
    def test_complete_output_no_missing(self):
        output = _complete_regex_output()
        missing = find_missing_fields(output)
        # Only optional fields that are not present should be missing.
        # supplier_name, total_amount are required and present.
        # All other VALID_FIELDS that are present are not missing.
        assert "supplier_name" not in missing
        assert "total_amount" not in missing

    def test_partial_output_missing_fields(self):
        output = _partial_regex_output()
        missing = find_missing_fields(output)
        assert "supplier_nif" in missing
        assert "invoice_number" in missing
        assert "invoice_date" in missing
        assert "base_amount" in missing
        assert "vat_rate" in missing
        assert "vat_amount" in missing
        assert "supplier_name" not in missing
        assert "total_amount" not in missing
        assert "currency" not in missing

    def test_invalid_value_counted_as_missing(self):
        output = {
            "supplier_name": _make_field("Acme Corp"),
            "total_amount": _make_field("121.00"),
            "invoice_date": _make_field("."),  # Invalid value
        }
        missing = find_missing_fields(output)
        assert "invoice_date" in missing
        assert "supplier_name" not in missing
        assert "total_amount" not in missing

    def test_empty_value_counted_as_missing(self):
        output = {
            "supplier_name": _make_field("Acme Corp"),
            "total_amount": _make_field("121.00"),
            "currency": _make_field(""),  # Empty
        }
        missing = find_missing_fields(output)
        assert "currency" in missing


# --- Tests: should_use_llm ---


class TestShouldUseLLM:
    def test_complete_output_no_llm(self, llm_settings):
        output = _complete_regex_output()
        assert should_use_llm(output) is False

    def test_partial_output_use_llm(self, llm_settings):
        output = _partial_regex_output()
        assert should_use_llm(output) is True

    def test_disabled_no_llm(self, llm_disabled):
        output = _partial_regex_output()
        assert should_use_llm(output) is False

    def test_not_configured_no_llm(self, llm_not_configured):
        output = _partial_regex_output()
        assert should_use_llm(output) is False

    def test_too_few_fields_no_llm(self, llm_settings):
        # Only 1 valid field: not enough to justify LLM.
        output = {
            "supplier_name": _make_field("Acme Corp"),
        }
        assert should_use_llm(output) is False

    def test_no_required_field_no_llm(self, llm_settings):
        # Has 2+ fields but no required field.
        output = {
            "currency": _make_field("EUR"),
            "invoice_number": _make_field("INV-001"),
        }
        assert should_use_llm(output) is False


# --- Tests: extract_with_llm ---


class TestExtractWithLLM:
    @patch("backend.services.llm_extraction.requests.post")
    def test_successful_extraction(self, mock_post, llm_settings):
        """LLM returns valid JSON with the requested fields."""
        llm_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "invoice_date": "2024-01-15",
                            "base_amount": "100.00",
                            "vat_rate": "21",
                            "vat_amount": "21.00",
                        })
                    }
                }
            ]
        }
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: llm_response,
            raise_for_status=lambda: None,
        )

        result = extract_with_llm(
            "Invoice text here...",
            ["invoice_date", "base_amount", "vat_rate", "vat_amount"],
        )

        assert result.success is True
        assert result.model == "test-model"
        assert result.fields == {
            "invoice_date": "2024-01-15",
            "base_amount": "100.00",
            "vat_rate": "21",
            "vat_amount": "21.00",
        }

    @patch("backend.services.llm_extraction.requests.post")
    def test_partial_fields(self, mock_post, llm_settings):
        """LLM returns only some of the requested fields."""
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
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: llm_response,
            raise_for_status=lambda: None,
        )

        result = extract_with_llm(
            "Invoice text...",
            ["invoice_date", "base_amount", "vat_rate", "vat_amount"],
        )

        assert result.success is True
        # Only fields with valid values are returned.
        assert "invoice_date" in result.fields
        assert "vat_rate" in result.fields
        assert "base_amount" not in result.fields
        assert "vat_amount" not in result.fields

    @patch("backend.services.llm_extraction.requests.post")
    def test_invalid_json_response(self, mock_post, llm_settings):
        """LLM returns non-JSON content."""
        llm_response = {
            "choices": [
                {
                    "message": {
                        "content": "I cannot extract the fields. Sorry."
                    }
                }
            ]
        }
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: llm_response,
            raise_for_status=lambda: None,
        )

        result = extract_with_llm("Text...", ["invoice_date"])
        assert result.success is False
        assert "parse" in result.error.lower() or "json" in result.error.lower()

    @patch("backend.services.llm_extraction.requests.post")
    def test_json_in_markdown(self, mock_post, llm_settings):
        """LLM wraps JSON in markdown code block."""
        llm_response = {
            "choices": [
                {
                    "message": {
                        "content": 'Here is the result:\n```json\n{"invoice_date": "2024-01-15"}\n```'
                    }
                }
            ]
        }
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: llm_response,
            raise_for_status=lambda: None,
        )

        result = extract_with_llm("Text...", ["invoice_date"])
        assert result.success is True
        assert result.fields == {"invoice_date": "2024-01-15"}

    @patch("backend.services.llm_extraction.requests.post")
    def test_timeout(self, mock_post, llm_settings):
        """LLM request times out."""
        import requests as req
        mock_post.side_effect = req.Timeout("Connection timed out")

        result = extract_with_llm("Text...", ["invoice_date"])
        assert result.success is False
        assert "timeout" in result.error.lower()

    @patch("backend.services.llm_extraction.requests.post")
    def test_connection_error(self, mock_post, llm_settings):
        """LLM connection fails."""
        import requests as req
        mock_post.side_effect = req.ConnectionError("Connection refused")

        result = extract_with_llm("Text...", ["invoice_date"])
        assert result.success is False
        assert "connection" in result.error.lower()

    @patch("backend.services.llm_extraction.requests.post")
    def test_http_500_retry_then_fail(self, mock_post, llm_settings):
        """LLM returns 500 on all attempts."""
        import requests as req

        def raise_500(*args, **kwargs):
            err = req.HTTPError("500 Server Error")
            err.response = MagicMock(status_code=500, text="Internal Server Error")
            raise err

        mock_post.side_effect = raise_500

        result = extract_with_llm("Text...", ["invoice_date"])
        assert result.success is False
        assert "500" in result.error

    @patch("backend.services.llm_extraction.requests.post")
    def test_http_400_no_retry(self, mock_post, llm_settings):
        """LLM returns 400 (non-retryable)."""
        import requests as req

        def raise_400(*args, **kwargs):
            err = req.HTTPError("400 Bad Request")
            err.response = MagicMock(status_code=400, text="Bad Request")
            raise err

        mock_post.side_effect = raise_400

        result = extract_with_llm("Text...", ["invoice_date"])
        assert result.success is False
        assert "400" in result.error
        # Should only be called once (no retry for 4xx).
        assert mock_post.call_count == 1

    def test_empty_missing_fields(self, llm_settings):
        """No missing fields: returns success with no fields."""
        result = extract_with_llm("Text...", [])
        assert result.success is True
        assert result.fields == {}


# --- Tests: merge_llm_results ---


class TestMergeLLMResults:
    def test_adds_missing_fields(self):
        raw_output = {
            "supplier_name": _make_field("Acme Corp"),
            "total_amount": _make_field("121.00"),
        }
        llm_result = LLMExtractionResult(
            fields={"invoice_date": "2024-01-15", "currency": "EUR"},
            model="test-model",
            success=True,
        )

        merged = merge_llm_results(raw_output, llm_result)

        assert "invoice_date" in merged
        assert merged["invoice_date"]["raw_value"] == "2024-01-15"
        assert merged["invoice_date"]["confidence"] == 0.55
        assert merged["invoice_date"]["provenance"]["method"] == "llm_fallback"
        assert merged["invoice_date"]["provenance"]["model"] == "test-model"

    def test_does_not_override_existing_valid_fields(self):
        raw_output = {
            "supplier_name": _make_field("Acme Corp"),
            "total_amount": _make_field("121.00"),
            "invoice_date": _make_field("2024-01-15"),  # Already present
        }
        llm_result = LLMExtractionResult(
            fields={"invoice_date": "2024-06-01"},  # Different value
            model="test-model",
            success=True,
        )

        merged = merge_llm_results(raw_output, llm_result)

        # Existing valid field is NOT overridden.
        assert merged["invoice_date"]["raw_value"] == "2024-01-15"
        assert merged["invoice_date"]["provenance"]["method"] == "pdf_text_rules"

    def test_overrides_invalid_existing_fields(self):
        raw_output = {
            "supplier_name": _make_field("Acme Corp"),
            "total_amount": _make_field("121.00"),
            "invoice_date": _make_field("."),  # Invalid
        }
        llm_result = LLMExtractionResult(
            fields={"invoice_date": "2024-01-15"},
            model="test-model",
            success=True,
        )

        merged = merge_llm_results(raw_output, llm_result)

        # Invalid field IS overridden.
        assert merged["invoice_date"]["raw_value"] == "2024-01-15"
        assert merged["invoice_date"]["provenance"]["method"] == "llm_fallback"

    def test_failed_llm_result_no_merge(self):
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


# --- Tests: _parse_llm_json ---


class TestParseLLMJson:
    def test_pure_json(self):
        content = '{"invoice_date": "2024-01-15"}'
        result = _parse_llm_json(content, ["invoice_date"])
        assert result == {"invoice_date": "2024-01-15"}

    def test_markdown_wrapped(self):
        content = '```json\n{"invoice_date": "2024-01-15"}\n```'
        result = _parse_llm_json(content, ["invoice_date"])
        assert result == {"invoice_date": "2024-01-15"}

    def test_json_with_surrounding_text(self):
        content = 'Here is the result: {"invoice_date": "2024-01-15"} Hope that helps!'
        result = _parse_llm_json(content, ["invoice_date"])
        assert result == {"invoice_date": "2024-01-15"}

    def test_no_json(self):
        content = "I cannot help with that."
        result = _parse_llm_json(content, ["invoice_date"])
        assert result is None

    def test_invalid_json(self):
        content = '{"invoice_date": "2024-01-15"'  # Missing closing brace
        result = _parse_llm_json(content, ["invoice_date"])
        assert result is None
