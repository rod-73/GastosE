"""Extraction methods: deterministic cascade (XML -> PDF text -> OCR -> LLM).

Each method reads the document content and returns a raw extraction output
dict. The output is then validated against the strict schema (VR-SCHEMA-1).

Deterministic first philosophy:
- XML: parse structured invoice (Facturae, e-invoice) => highest confidence.
- PDF text: extract text layer and apply regex rules => medium confidence.
- OCR: stub (not implemented in V2-S1; requires Tesseract).
- LLM: stub (not implemented in V2-S1; requires ExtractionLLM, ADR-0010).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional


def extract_xml(content: bytes) -> Dict[str, Any]:
    """Extract fields from an XML invoice (Facturae / e-invoice).

    Deterministic: parses the XML structure directly. Confidence is high
    (0.95-1.0) because the data is structured.

    Supports:
    - Facturae 3.2 (Spanish e-invoice standard)
    - Generic XML invoices with common field names
    """
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        return _error_output(f"XML parse error: {e}")

    fields: Dict[str, Any] = {}
    method = "xml_schema"

    # Try Facturae 3.2 structure first.
    # Namespace: urn:es:febom:facturae:3.2
    ns = {
        "f": "urn:es:febom:facturae:3.2",
        "c": "urn:es:febom:facturae:3.2:common",
    }

    # Supplier name
    supplier_name = _find_text(root, ns, [
        ".//f:Emisor/f:Nombre",
        ".//c:Emisor/c:Nombre",
        ".//f:Emisor/f:NombreComercial",
    ])
    if supplier_name:
        fields["supplier_name"] = _make_field(
            supplier_name, 0.98, method, "xml:Emisor/Nombre"
        )

    # Supplier NIF
    supplier_nif = _find_text(root, ns, [
        ".//f:Emisor/f:NIF",
        ".//c:Emisor/c:NIF",
        ".//f:Emisor/f:ID/c:IDTipo",
    ])
    if supplier_nif:
        fields["supplier_nif"] = _make_field(
            supplier_nif, 0.98, method, "xml:Emisor/NIF"
        )

    # Invoice number
    invoice_number = _find_text(root, ns, [
        ".//f:Referencia",
        ".//f:Numero",
        ".//c:Referencia",
    ])
    if invoice_number:
        fields["invoice_number"] = _make_field(
            invoice_number, 0.97, method, "xml:Referencia"
        )

    # Invoice date
    invoice_date = _find_text(root, ns, [
        ".//f:FechaEmision",
        ".//c:FechaEmision",
        ".//f:Fecha",
    ])
    if invoice_date:
        fields["invoice_date"] = _make_field(
            invoice_date, 0.97, method, "xml:FechaEmision"
        )

    # Total amount
    total_amount = _find_text(root, ns, [
        ".//f:ImporteTotal",
        ".//c:ImporteTotal",
        ".//f:Importe/f:ImporteTotal",
    ])
    if total_amount:
        fields["total_amount"] = _make_field(
            total_amount, 0.99, method, "xml:ImporteTotal"
        )

    # Base amount
    base_amount = _find_text(root, ns, [
        ".//f:BaseImponible",
        ".//c:BaseImponible",
    ])
    if base_amount:
        fields["base_amount"] = _make_field(
            base_amount, 0.97, method, "xml:BaseImponible"
        )

    # VAT rate
    vat_rate = _find_text(root, ns, [
        ".//f:Tipo",
        ".//c:Tipo",
    ])
    if vat_rate:
        fields["vat_rate"] = _make_field(
            vat_rate, 0.95, method, "xml:TipoIVA"
        )

    # VAT amount
    vat_amount = _find_text(root, ns, [
        ".//f:Cuota",
        ".//c:Cuota",
    ])
    if vat_amount:
        fields["vat_amount"] = _make_field(
            vat_amount, 0.95, method, "xml:CuotaIVA"
        )

    # Currency
    currency = _find_text(root, ns, [
        ".//f:Moneda",
        ".//c:Moneda",
    ])
    if currency:
        fields["currency"] = _make_field(
            currency, 0.95, method, "xml:Moneda"
        )

    # Fallback: try generic XML structure (no namespace).
    if not fields:
        fields = _extract_generic_xml(root)

    if not fields:
        return _error_output("No extractable fields found in XML")

    return fields


def _extract_generic_xml(root: ET.Element) -> Dict[str, Any]:
    """Extract from generic XML without known namespace."""
    fields: Dict[str, Any] = {}
    method = "xml_schema"

    # Search all elements for common field names.
    for elem in root.iter():
        tag = elem.tag.lower()
        if "namespace" in tag:
            tag = tag.split("}")[-1]

        if elem.text and elem.text.strip():
            text = elem.text.strip()
            if tag in ("suppliername", "supplier", "emisor", "vendor"):
                if "supplier_name" not in fields:
                    fields["supplier_name"] = _make_field(
                        text, 0.90, method, f"xml:{elem.tag}"
                    )
            elif tag in ("nif", "cif", "taxid", "vatnumber"):
                if "supplier_nif" not in fields:
                    fields["supplier_nif"] = _make_field(
                        text, 0.90, method, f"xml:{elem.tag}"
                    )
            elif tag in ("invoicenumber", "number", "referencia", "invoiceid"):
                if "invoice_number" not in fields:
                    fields["invoice_number"] = _make_field(
                        text, 0.90, method, f"xml:{elem.tag}"
                    )
            elif tag in ("invoicedate", "date", "fecha", "issuedate"):
                if "invoice_date" not in fields:
                    fields["invoice_date"] = _make_field(
                        text, 0.90, method, f"xml:{elem.tag}"
                    )
            elif tag in ("total", "totalamount", "importetotal", "grandtotal"):
                if "total_amount" not in fields:
                    fields["total_amount"] = _make_field(
                        text, 0.92, method, f"xml:{elem.tag}"
                    )
            elif tag in ("baseamount", "baseimponible", "netamount"):
                if "base_amount" not in fields:
                    fields["base_amount"] = _make_field(
                        text, 0.90, method, f"xml:{elem.tag}"
                    )
            elif tag in ("vatrate", "taxrate", "tipova"):
                if "vat_rate" not in fields:
                    fields["vat_rate"] = _make_field(
                        text, 0.88, method, f"xml:{elem.tag}"
                    )
            elif tag in ("vatamount", "taxamount", "cuotaiva"):
                if "vat_amount" not in fields:
                    fields["vat_amount"] = _make_field(
                        text, 0.88, method, f"xml:{elem.tag}"
                    )
            elif tag in ("currency", "moneda"):
                if "currency" not in fields:
                    fields["currency"] = _make_field(
                        text, 0.90, method, f"xml:{elem.tag}"
                    )

    return fields


def extract_pdf_text(content: bytes) -> Dict[str, Any]:
    """Extract fields from a PDF with text layer using regex rules.

    Deterministic: applies pattern matching to the extracted text.
    Confidence is medium (0.6-0.85) because text extraction may be
    imperfect and patterns may match incorrectly.

    Note: This is a simplified implementation. In production, a proper
    PDF text extraction library (pdfminer, pypdf) would be used. Here we
    treat the content as raw text for the text layer.
    """
    method = "pdf_text_rules"

    # For the simplified implementation, decode the content as text.
    # In production, this would use a PDF library to extract the text layer.
    try:
        text = content.decode("utf-8", errors="ignore")
    except Exception:
        text = ""

    # If the content starts with %PDF-, we can't extract text without a
    # proper PDF library. Return an error for now.
    if content.startswith(b"%PDF-"):
        return _error_output(
            "PDF text extraction requires a PDF library (pdfminer/pypdf). "
            "Not available in current runtime."
        )

    fields: Dict[str, Any] = {}

    # Supplier name: look for common patterns.
    # Pattern: "Supplier: <name>" or "Proveedor: <name>" or "Facturado a: <name>"
    m = re.search(
        r"(?:Supplier|Proveedor|Facturado\s+a|De)\s*:\s*(.+?)(?:\n|$)",
        text,
        re.IGNORECASE,
    )
    if m:
        fields["supplier_name"] = _make_field(
            m.group(1).strip(), 0.70, method, "regex:supplier"
        )

    # NIF/CIF: Spanish tax ID pattern.
    m = re.search(
        r"(?:NIF|CIF|NIF/CIF)\s*:\s*([A-Z]\d{7}[A-Z0-9]|\d{8}[A-Z])",
        text,
        re.IGNORECASE,
    )
    if m:
        fields["supplier_nif"] = _make_field(
            m.group(1).strip(), 0.85, method, "regex:nif"
        )

    # Invoice number.
    m = re.search(
        r"(?:Invoice\s*(?:No|Number|#)|N[°º]?\s*(?:de\s*)?Factura|Factura\s*(?:N[°º]|n[°º]))\s*[:#]?\s*([A-Z0-9\-/]+)",
        text,
        re.IGNORECASE,
    )
    if m:
        fields["invoice_number"] = _make_field(
            m.group(1).strip(), 0.75, method, "regex:invoice_number"
        )

    # Invoice date: ISO or Spanish format.
    m = re.search(
        r"(?:Date|Fecha)\s*:\s*(\d{4}-\d{2}-\d{2}|\d{2}[/-]\d{2}[/-]\d{4})",
        text,
        re.IGNORECASE,
    )
    if m:
        fields["invoice_date"] = _make_field(
            m.group(1).strip(), 0.80, method, "regex:date"
        )

    # Total amount: look for "Total: XX.XX" or "Importe Total: XX.XX".
    m = re.search(
        r"(?:Total|Importe\s*Total|Grand\s*Total)\s*:\s*([\d.,]+)",
        text,
        re.IGNORECASE,
    )
    if m:
        fields["total_amount"] = _make_field(
            m.group(1).strip(), 0.80, method, "regex:total"
        )

    # Base amount.
    m = re.search(
        r"(?:Base|Base\s*Imponible|Net\s*Amount)\s*:\s*([\d.,]+)",
        text,
        re.IGNORECASE,
    )
    if m:
        fields["base_amount"] = _make_field(
            m.group(1).strip(), 0.75, method, "regex:base"
        )

    # VAT rate.
    m = re.search(
        r"(?:IVA|VAT|Tax\s*Rate)\s*:\s*(\d{1,2}(?:[.,]\d{1,2})?)\s*%",
        text,
        re.IGNORECASE,
    )
    if m:
        fields["vat_rate"] = _make_field(
            m.group(1).strip(), 0.75, method, "regex:vat_rate"
        )

    # VAT amount.
    m = re.search(
        r"(?:IVA|VAT|Tax\s*Amount)\s*:\s*([\d.,]+)",
        text,
        re.IGNORECASE,
    )
    if m:
        fields["vat_amount"] = _make_field(
            m.group(1).strip(), 0.75, method, "regex:vat_amount"
        )

    # Currency.
    m = re.search(r"(?:Currency|Moneda)\s*:\s*([A-Z]{3})", text, re.IGNORECASE)
    if m:
        fields["currency"] = _make_field(
            m.group(1).strip(), 0.85, method, "regex:currency"
        )

    if not fields:
        return _error_output("No extractable fields found in PDF text")

    return fields


def extract_ocr(content: bytes) -> Dict[str, Any]:
    """OCR extraction (stub).

    Not implemented in V2-S1. Requires Tesseract OCR engine.
    Returns an error output that will cause the job to fail.
    """
    return _error_output(
        "OCR extraction not implemented (requires Tesseract). "
        "Will be available in a future slice."
    )


def extract_llm(content: bytes) -> Dict[str, Any]:
    """LLM/Vision extraction (stub).

    Not implemented in V2-S1. Requires ExtractionLLM abstraction (ADR-0010).
    Returns an error output that will cause the job to fail.
    """
    return _error_output(
        "LLM extraction not implemented (requires ExtractionLLM, ADR-0010). "
        "Will be available in a future slice."
    )


# --- Helpers ---


def _find_text(
    root: ET.Element, ns: Dict[str, str], paths: List[str]
) -> Optional[str]:
    """Find the first non-empty text among multiple XPath paths.

    Tries each path in order; returns the first non-empty result.
    """
    for path in paths:
        try:
            elem = root.find(path, ns)
        except Exception:
            continue
        if elem is not None and elem.text and elem.text.strip():
            return elem.text.strip()
    return None


def _make_field(
    raw_value: str, confidence: float, method: str, rule: str
) -> Dict[str, Any]:
    """Build a single field extraction dict."""
    return {
        "raw_value": raw_value,
        "confidence": confidence,
        "provenance": {
            "method": method,
            "rule": rule,
        },
    }


def _error_output(reason: str) -> Dict[str, Any]:
    """Build an error output that will fail schema validation."""
    return {"_error": reason}


# --- Cascade selection ---

# Maps format_detected -> extraction method function.
FORMAT_TO_METHOD = {
    "xml": ("xml_schema", extract_xml),
    "pdf_text": ("pdf_text_rules", extract_pdf_text),
    "pdf_scanned": ("ocr", extract_ocr),
    "image": ("vision_llm", extract_llm),
}


def select_method(format_detected: str) -> tuple[str, Any]:
    """Select the extraction method based on the detected format.

    Returns (method_name, method_function).
    """
    if format_detected in FORMAT_TO_METHOD:
        return FORMAT_TO_METHOD[format_detected]
    # Default: try PDF text rules.
    return FORMAT_TO_METHOD["pdf_text"]
