from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path

import fitz

from domains.invoice_enrichment.document_metadata import (
    extract_invoice_ref,
    extract_issue_date,
)
from domains.invoice_enrichment.models import ProcessedInvoiceResult
from domains.invoice_enrichment.pdf_document.models import HeaderMetadata


def display_currency(result: ProcessedInvoiceResult) -> str:
    if result.currency:
        return result.currency
    if result.descriptions:
        return result.descriptions[0].currency
    if result.line_items:
        return result.line_items[0].currency
    return "CUR"


class TotalsRenderer:
    def __init__(self, margin_x: float, margin_bottom: float) -> None:
        self._margin_x = margin_x
        self._margin_bottom = margin_bottom

    def draw_totals(
        self,
        page: fitz.Page,
        result: ProcessedInvoiceResult,
        y: float,
    ) -> None:
        total_qty = self._sum_decimal(entry.quantity for entry in result.descriptions)
        total_value = self._sum_decimal(
            (entry.line_value for entry in result.descriptions),
            force_two_decimals=True,
        )
        currency = display_currency(result)
        start_y = min(y, page.rect.height - self._margin_bottom - 28)
        start_x = self._margin_x
        page.insert_text(
            fitz.Point(start_x, start_y),
            f"Total units / Lacznie: {total_qty} sztuk",
            fontsize=10,
            fontname="helv",
        )
        page.insert_text(
            fitz.Point(start_x, start_y + 13),
            f"Total value / Wartosc calkowita ({currency}): {self._format_total_value(total_value, currency)}",
            fontsize=10,
            fontname="helv",
        )

    def resolve_header_metadata(
        self,
        result: ProcessedInvoiceResult,
        src_doc: fitz.Document | None,
    ) -> HeaderMetadata:
        invoice_ref = result.document_ref or result.invoice_number
        issue_date = result.issue_date
        document_type = result.document_type

        if src_doc is not None:
            parsed_ref, parsed_issue_date = self._extract_pdf_metadata(src_doc)
            invoice_ref = parsed_ref or invoice_ref
            issue_date = issue_date or parsed_issue_date

        if not invoice_ref:
            invoice_ref = self._display_invoice_ref(result)

        return HeaderMetadata(
            document_type=document_type,
            invoice_ref=invoice_ref,
            issue_date=issue_date,
        )

    def _extract_pdf_metadata(
        self, src_doc: fitz.Document
    ) -> tuple[str | None, str | None]:
        try:
            text = src_doc[0].get_text("text")
        except Exception:
            return None, None

        invoice_ref = extract_invoice_ref(text)
        issue_date = extract_issue_date(text)
        return invoice_ref, issue_date

    def _display_invoice_ref(self, result: ProcessedInvoiceResult) -> str:
        if result.invoice_number:
            return result.invoice_number
        if result.source_filename:
            return Path(result.source_filename).stem
        return result.order_id

    def _sum_decimal(self, values, *, force_two_decimals: bool = False) -> str:
        total = Decimal("0")
        for value in values:
            normalized = value.replace(" ", "").replace(",", ".")
            try:
                total += Decimal(normalized)
            except (InvalidOperation, AttributeError):
                continue
        if force_two_decimals:
            return f"{total:.2f}"
        if total == total.to_integral():
            return str(total.quantize(Decimal("1")))
        return f"{total:.2f}"

    def _format_total_value(self, value: str, currency: str) -> str:
        if currency in {"EUR", "PLN"}:
            return value.replace(".", ",")
        return value
