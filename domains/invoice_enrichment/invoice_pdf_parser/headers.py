from __future__ import annotations

from core.utils import collapse_whitespace
from domains.invoice_enrichment.invoice_pdf_parser.parsing_error import ParsingError
from domains.invoice_enrichment.invoice_pdf_parser.models import (
    HeaderContext,
    PhysicalRow,
)


class HeaderDetector:
    def __init__(
        self,
        required_tokens: tuple[str, ...],
        supported_currencies: tuple[str, ...],
    ) -> None:
        self._required_tokens = required_tokens
        self._supported_currencies = supported_currencies

    def find_header_rows(self, rows: list[PhysicalRow]) -> HeaderContext | None:
        for index, row in enumerate(rows):
            text = collapse_whitespace(
                " ".join(word["text"] for word in row.words)
            ).lower()
            if all(token in text for token in self._required_tokens):
                header_rows = [row]
                next_index = index + 1
                while next_index < len(rows):
                    next_row = rows[next_index]
                    if next_row.top - header_rows[-1].top > 14:
                        break
                    header_rows.append(next_row)
                    next_index += 1
                combined_header_text = " ".join(
                    collapse_whitespace(
                        " ".join(word["text"] for word in header_row.words)
                    ).lower()
                    for header_row in header_rows
                )
                return HeaderContext(
                    rows=header_rows, has_origin="origin" in combined_header_text
                )
        return None

    def detect_currency(
        self,
        header_rows: list[PhysicalRow],
        rows: list[PhysicalRow],
    ) -> str:
        for source_rows in (header_rows, rows):
            currencies = [
                word["text"].strip().upper()
                for row in source_rows
                for word in row.words
                if word["text"].strip().upper() in self._supported_currencies
            ]
            if currencies:
                return currencies[0]
        raise ParsingError("Could not determine invoice currency from the PDF table")
