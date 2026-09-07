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


def _extract_pdf_text_with_pypdf(content: bytes) -> str:
    """Extract text from PDF using pypdf library.
    
    Returns empty string if extraction fails.
    """
    try:
        from pypdf import PdfReader
        from io import BytesIO
        
        reader = PdfReader(BytesIO(content))
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        return "\n".join(text_parts)
    except Exception:
        return ""


def extract_pdf_text(content: bytes) -> Dict[str, Any]:
    """Extract fields from a PDF with text layer using regex rules.

    Deterministic: applies pattern matching to the extracted text.
    Confidence is medium (0.6-0.85) because text extraction may be
    imperfect and patterns may match incorrectly.

    Uses pypdf to extract the text layer from the PDF.
    """
    method = "pdf_text_rules"

    # Extract text from PDF using pypdf.
    text = _extract_pdf_text_with_pypdf(content)
    
    if not text:
        # Fallback: try to decode as UTF-8 (for non-PDF or corrupted files).
        try:
            text = content.decode("utf-8", errors="ignore")
        except Exception:
            text = ""

    if not text:
        return _error_output("No text could be extracted from PDF")

    fields: Dict[str, Any] = {}

    # Supplier name: look for common patterns.
    # Patterns: "Supplier: <name>", "Proveedor: <name>", "Facturado a: <name>",
    # or the first line of the document (often the supplier name).
    m = re.search(
        r"(?:Supplier|Proveedor|Facturado\s+a|De|Emitida\s+por)\s*:\s*(.+?)(?:\n|$)",
        text,
        re.IGNORECASE,
    )
    if m:
        fields["supplier_name"] = _make_field(
            m.group(1).strip(), 0.70, method, "regex:supplier"
        )
    else:
        # Fallback: first non-empty line (often supplier name).
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if lines:
            # Heuristic: if first line looks like a company name (has spaces, no digits).
            first_line = lines[0]
            # Remove address parts after "·" or "," if present.
            supplier_candidate = re.split(r"[·,]", first_line)[0].strip()
            if len(supplier_candidate) > 3 and not re.search(r"\d{4}", supplier_candidate):
                fields["supplier_name"] = _make_field(
                    supplier_candidate, 0.60, method, "heuristic:first_line"
                )

    # NIF/CIF: Spanish tax ID pattern (flexible).
    m = re.search(
        r"(?:NIF|CIF|NIF/CIF|N\.?I\.?F\.?|C\.?I\.?F\.?)\s*[:\-]?\s*([A-Z]\d{7}[A-Z0-9]|\d{8}[A-Z]|[A-Z]{2}\d{6}[A-Z0-9])",
        text,
        re.IGNORECASE,
    )
    if m:
        fields["supplier_nif"] = _make_field(
            m.group(1).strip(), 0.85, method, "regex:nif"
        )

    # Invoice number: flexible patterns.
    # "N.° de factura: 202787099888", "Invoice No: 12345", "Factura #12345"
    m = re.search(
        r"(?:N[°º.]*\s*(?:de\s*)?factura|Invoice\s*(?:No|Number|#)|Factura\s*(?:N[°º]|n[°º]|#)|N[°º.]*\s*factura)\s*[:#]?\s*([A-Z0-9\-/]+)",
        text,
        re.IGNORECASE,
    )
    if m:
        fields["invoice_number"] = _make_field(
            m.group(1).strip(), 0.75, method, "regex:invoice_number"
        )

    # Invoice date: flexible patterns.
    # "Fecha de facturación: 02/09/26", "Date: 2026-09-02", "Fecha: 02/09/2026"
    # Also handles: "7/9/2026" (D/M/YYYY without leading zeros)
    m = re.search(
        r"(?:Fecha\s*(?:de\s*facturaci[oó]n|de\s*emisi[oó]n)?|Date|Fecha\s*factura)\s*[:\-]?\s*(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        text,
        re.IGNORECASE,
    )
    if m:
        fields["invoice_date"] = _make_field(
            m.group(1).strip(), 0.80, method, "regex:date"
        )

    # Total amount: flexible patterns.
    # "Total a pagar 25,06 EUR", "Total: 25.06", "Importe Total: 25,06"
    m = re.search(
        r"(?:Total\s*(?:a\s*pagar|final|general)?|Importe\s*Total|Grand\s*Total|Total)\s*[:\-]?\s*([\d.,]+)\s*(?:EUR|USD|€|\$)?",
        text,
        re.IGNORECASE,
    )
    if m:
        fields["total_amount"] = _make_field(
            m.group(1).strip(), 0.80, method, "regex:total"
        )

    # Base amount: flexible patterns.
    # "Total (base imponible) 20,71 EUR", "Base: 20.71", "Net Amount: 20,71"
    m = re.search(
        r"(?:Total\s*\(base\s*imponible\)|Base\s*(?:imponible)?|Net\s*Amount|Subtotal)\s*[:\-]?\s*([\d.,]+)\s*(?:EUR|USD|€|\$)?",
        text,
        re.IGNORECASE,
    )
    if m:
        fields["base_amount"] = _make_field(
            m.group(1).strip(), 0.75, method, "regex:base"
        )

    # VAT rate: flexible patterns.
    # "IVA (21,0 %)", "VAT: 21%", "Tax Rate: 21.0%", "21,0 %"
    m = re.search(
        r"(?:IVA|VAT|Tax\s*Rate|Tipo\s*IVA)\s*\(?\s*(\d{1,2}(?:[.,]\d{1,2})?)\s*%\s*\)?",
        text,
        re.IGNORECASE,
    )
    if m:
        fields["vat_rate"] = _make_field(
            m.group(1).strip(), 0.75, method, "regex:vat_rate"
        )
    else:
        # Fallback: look for percentage near "IVA" or "VAT".
        m = re.search(
            r"(?:IVA|VAT)[^\d]*(\d{1,2}(?:[.,]\d{1,2})?)\s*%",
            text,
            re.IGNORECASE,
        )
        if m:
            fields["vat_rate"] = _make_field(
                m.group(1).strip(), 0.70, method, "regex:vat_rate_fallback"
            )

    # VAT amount: flexible patterns.
    # "+ IVA (21,0 %) 4,35 EUR", "VAT: 4.35", "Tax Amount: 4,35"
    m = re.search(
        r"(?:\+\s*)?(?:IVA|VAT|Tax\s*Amount|Importe\s*IVA)\s*\(?\s*(?:\d{1,2}(?:[.,]\d{1,2})?\s*%\s*\)?)?\s*[:\-]?\s*([\d.,]+)\s*(?:EUR|USD|€|\$)?",
        text,
        re.IGNORECASE,
    )
    if m:
        fields["vat_amount"] = _make_field(
            m.group(1).strip(), 0.75, method, "regex:vat_amount"
        )

    # Currency: prefer currency associated with amounts/totals.
    # Strategy:
    # 1. Look for currency near "TOTAL", "IMPORTE", "Amount" (high confidence).
    # 2. Look for currency followed by a number (e.g., "EUR 147,96").
    # 3. Fallback: first occurrence in text.
    currency = None
    confidence = 0.70
    rule = "regex:currency"

    # 1. Currency near total/amount keywords.
    m = re.search(
        r"(?:TOTAL|IMPORTE|Amount|Total|Importe)[^\n]*?\b(EUR|USD|GBP|MXN|€|\$)\b",
        text, re.IGNORECASE,
    )
    if not m:
        m = re.search(
            r"\b(EUR|USD|GBP|MXN|€|\$)\b[^\n]*?(?:TOTAL|IMPORTE|Amount|Total|Importe)",
            text, re.IGNORECASE,
        )
    if m:
        currency = m.group(1)
        confidence = 0.90
        rule = "regex:currency_near_total"
    else:
        # 2. Currency followed by a numeric amount.
        m = re.search(
            r"\b(EUR|USD|GBP|MXN|€|\$)\b\s*[\d.,]+",
            text,
        )
        if m:
            currency = m.group(1)
            confidence = 0.80
            rule = "regex:currency_before_amount"
        else:
            # 3. Fallback: first occurrence.
            m = re.search(r"\b(EUR|USD|GBP|MXN|€|\$)\b", text)
            if m:
                currency = m.group(1)
                confidence = 0.70
                rule = "regex:currency_first"

    if currency:
        # Normalize symbols to codes.
        if currency == "€":
            currency = "EUR"
        elif currency == "$":
            currency = "USD"
        fields["currency"] = _make_field(
            currency, confidence, method, rule
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
