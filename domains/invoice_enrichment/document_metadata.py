from __future__ import annotations

import re

from domains.invoice_enrichment.models import DocumentType

COMMERCIAL_INVOICE_PATTERN = re.compile(
    r"Commercial\s+Invoice\s+nr\s+([A-Z0-9]+(?:[/-][A-Z0-9]+)+)",
    re.IGNORECASE,
)
INTER_STORE_SHIFT_PATTERN = re.compile(
    r"Inter-Store\s+Shift\s+nr\s+([A-Z0-9]+(?:[/-][A-Z0-9]+)+)",
    re.IGNORECASE,
)
ISSUE_DATE_PATTERN = re.compile(
    r"(?:Data\s+wystawienia|Issue\s+date)(?:\s*/\s*Issue\s+date)?\s*:\s*(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)


def detect_document_identity(first_page_text: str) -> tuple[DocumentType, str | None]:
    if match := INTER_STORE_SHIFT_PATTERN.search(first_page_text):
        return "inter_store_shift", match.group(1).strip()
    if match := COMMERCIAL_INVOICE_PATTERN.search(first_page_text):
        return "commercial_invoice", match.group(1).strip()
    return "unknown", None


def extract_issue_date(text: str) -> str | None:
    match = ISSUE_DATE_PATTERN.search(text)
    return match.group(1).strip() if match else None


def extract_invoice_ref(text: str) -> str | None:
    if match := INTER_STORE_SHIFT_PATTERN.search(text):
        return match.group(1).strip()
    match = COMMERCIAL_INVOICE_PATTERN.search(text)
    if not match:
        return None
    return match.group(1).strip()
