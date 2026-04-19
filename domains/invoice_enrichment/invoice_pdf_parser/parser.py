from __future__ import annotations

import re
from io import BytesIO

import pdfplumber

from core.utils import collapse_whitespace
from domains.invoice_enrichment.document_metadata import (
    detect_document_identity,
    extract_issue_date,
)
from domains.invoice_enrichment.invoice_pdf_parser.columns import ColumnDetector
from domains.invoice_enrichment.invoice_pdf_parser.parsing_error import ParsingError
from domains.invoice_enrichment.invoice_pdf_parser.headers import HeaderDetector
from domains.invoice_enrichment.invoice_pdf_parser.items import ItemCollector
from domains.invoice_enrichment.invoice_pdf_parser.models import (
    PageTableContext,
    PhysicalRow,
)
from domains.invoice_enrichment.invoice_pdf_parser.rows import RowGrouper
from domains.invoice_enrichment.invoice_pdf_parser.validation import ItemValidator
from domains.invoice_enrichment.models import InvoiceLineItem, ParsedDocument


class Parser:
    HS_CODE_PATTERN = re.compile(r"\b\d{4}\.\d{2}\.\d{4}\b")
    LINE_NUMBER_PATTERN = re.compile(r"^\d{1,4}$")
    SUPPORTED_CURRENCIES = ("USD", "EUR", "PLN")
    END_KEYWORDS = (
        "razem do zaplaty",
        "zaplacono",
        "pozostaje",
        "podpis",
        "kurs przeliczenia",
        "slownie",
    )
    ROW_TOLERANCE = 4.0
    HEADER_REQUIRED_TOKENS = ("lp", "description", "hs", "qty")

    def __init__(self) -> None:
        self._row_grouper = RowGrouper(row_tolerance=self.ROW_TOLERANCE)
        self._header_detector = HeaderDetector(
            required_tokens=self.HEADER_REQUIRED_TOKENS,
            supported_currencies=self.SUPPORTED_CURRENCIES,
        )
        self._column_detector = ColumnDetector()
        self._item_collector = ItemCollector(
            line_number_pattern=self.LINE_NUMBER_PATTERN,
            hs_code_pattern=self.HS_CODE_PATTERN,
            end_keywords=self.END_KEYWORDS,
        )
        self._validator = ItemValidator(
            extract_hs_code=self._item_collector.extract_hs_code,
        )

    def parse(self, pdf_bytes: bytes) -> ParsedDocument:
        items: list[InvoiceLineItem] = []
        document_type = "unknown"
        document_ref: str | None = None
        issue_date: str | None = None
        currency: str | None = None
        previous_context: PageTableContext | None = None

        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            for page_index, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                if page_index == 0:
                    document_type, document_ref = detect_document_identity(page_text)
                    issue_date = extract_issue_date(page_text)

                page_items, page_currency, previous_context = self._extract_page_items(
                    page, previous_context
                )
                items.extend(page_items)
                if not currency and page_currency:
                    currency = page_currency

        if not items:
            raise ParsingError("Could not extract any invoice line items from the PDF")

        self._validator.validate_items(items)
        return ParsedDocument(
            document_type=document_type,
            document_ref=document_ref,
            issue_date=issue_date,
            currency=currency,
            line_items=items,
        )

    def _extract_page_items(
        self,
        page: pdfplumber.page.Page,
        previous_context: PageTableContext | None,
    ) -> tuple[list[InvoiceLineItem], str | None, PageTableContext | None]:
        words = page.extract_words(
            x_tolerance=2,
            y_tolerance=2,
            keep_blank_chars=False,
            use_text_flow=False,
        )
        if not words:
            return (
                [],
                previous_context.currency if previous_context else None,
                previous_context,
            )

        rows = self._row_grouper.group_rows(words)
        header_context = self._header_detector.find_header_rows(rows)
        if header_context is not None:
            columns = self._column_detector.build_columns(header_context, page.width)
            currency = self._header_detector.detect_currency(header_context.rows, rows)
            items = self._item_collector.collect_items_from_rows(
                rows,
                columns=columns,
                currency=currency,
                has_origin=header_context.has_origin,
                start_after_top=header_context.rows[-1].top,
            )
            return (
                items,
                currency,
                PageTableContext(
                    columns=columns,
                    has_origin=header_context.has_origin,
                    currency=currency,
                ),
            )

        if previous_context is None:
            if self._looks_like_table_continuation(rows):
                raise ParsingError(
                    "Could not determine invoice table header on the first table page"
                )
            return [], None, None

        if not self._has_table_body_rows(rows, previous_context.columns):
            return [], previous_context.currency, previous_context

        items = self._item_collector.collect_items_from_rows(
            rows,
            columns=previous_context.columns,
            currency=previous_context.currency,
            has_origin=previous_context.has_origin,
            start_after_top=None,
        )
        if items:
            return items, previous_context.currency, previous_context

        if self._looks_like_table_continuation(rows):
            raise ParsingError("Could not parse continuation page of the invoice table")

        return [], previous_context.currency, previous_context

    def _looks_like_table_continuation(self, rows: list[PhysicalRow]) -> bool:
        for row in rows:
            row_text = collapse_whitespace(" ".join(word["text"] for word in row.words))
            if not row_text or self._item_collector.looks_like_end(row_text):
                continue
            if self.HS_CODE_PATTERN.search(row_text):
                return True
            if self.LINE_NUMBER_PATTERN.search(
                row_text
            ) and self._item_collector._row_contains_numeric_triplet(row_text):
                return True
        return False

    def _has_table_body_rows(
        self,
        rows: list[PhysicalRow],
        columns: dict[str, tuple[float, float]],
    ) -> bool:
        for row in rows:
            cells = self._item_collector.row_to_cells(row, columns)
            joined_text = " ".join(value for value in cells.values() if value)
            if not joined_text or self._item_collector.looks_like_end(joined_text):
                continue
            if self._item_collector.looks_like_item_start(cells, joined_text):
                return True
        return False
