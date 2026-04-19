from __future__ import annotations

from typing import Callable

from domains.invoice_enrichment.invoice_pdf_parser.parsing_error import ParsingError
from domains.invoice_enrichment.models import InvoiceLineItem


class ItemValidator:
    def __init__(self, extract_hs_code: Callable[[str], str]) -> None:
        self._extract_hs_code = extract_hs_code

    def validate_items(self, items: list[InvoiceLineItem]) -> None:
        line_numbers = [item.line_no for item in items]
        if len(line_numbers) != len(set(line_numbers)):
            raise ParsingError(
                "Invoice line numbers are duplicated; PDF generation aborted"
            )
        if line_numbers != sorted(line_numbers):
            raise ParsingError("Invoice line numbers are not strictly ascending")
        for item in items:
            if not item.item_name:
                raise ParsingError(
                    f"Invoice item name is empty for line {item.line_no}"
                )
            if not self._extract_hs_code(item.hs_code):
                raise ParsingError(
                    f"Invalid HS code for line {item.line_no}: {item.hs_code}"
                )
            for field_name in ("currency", "quantity", "unit_price", "line_value"):
                if not getattr(item, field_name):
                    raise ParsingError(f"{field_name} is empty for line {item.line_no}")
