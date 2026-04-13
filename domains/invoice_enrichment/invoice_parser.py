from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any

import pdfplumber

from core.utils import collapse_whitespace
from domains.invoice_enrichment.document_metadata import (
    detect_document_identity,
    extract_issue_date,
)
from domains.invoice_enrichment.models import InvoiceLineItem, ParsedDocument


class InvoiceParsingError(Exception):
    pass


@dataclass(slots=True)
class _PhysicalRow:
    top: float
    words: list[dict[str, Any]]


@dataclass(slots=True)
class _HeaderContext:
    rows: list[_PhysicalRow]
    has_origin: bool


@dataclass(slots=True)
class _PageTableContext:
    columns: dict[str, tuple[float, float]]
    has_origin: bool
    currency: str


class InvoicePdfParser:
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

    def parse(self, pdf_bytes: bytes) -> ParsedDocument:
        items: list[InvoiceLineItem] = []
        document_type = "unknown"
        document_ref: str | None = None
        issue_date: str | None = None
        currency: str | None = None
        previous_context: _PageTableContext | None = None

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
            raise InvoiceParsingError(
                "Could not extract any invoice line items from the PDF"
            )

        self._validate_items(items)
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
        previous_context: _PageTableContext | None,
    ) -> tuple[list[InvoiceLineItem], str | None, _PageTableContext | None]:
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

        rows = self._group_rows(words)
        header_context = self._find_header_rows(rows)
        if header_context is not None:
            columns = self._build_columns(header_context, page.width)
            currency = self._detect_currency(header_context.rows, rows)
            items = self._collect_items_from_rows(
                rows,
                columns=columns,
                currency=currency,
                has_origin=header_context.has_origin,
                start_after_top=header_context.rows[-1].top,
            )
            return (
                items,
                currency,
                _PageTableContext(
                    columns=columns,
                    has_origin=header_context.has_origin,
                    currency=currency,
                ),
            )

        if previous_context is None:
            if self._looks_like_table_continuation(rows):
                raise InvoiceParsingError(
                    "Could not determine invoice table header on the first table page"
                )
            return [], None, None

        if not self._has_table_body_rows(rows, previous_context.columns):
            return [], previous_context.currency, previous_context

        items = self._collect_items_from_rows(
            rows,
            columns=previous_context.columns,
            currency=previous_context.currency,
            has_origin=previous_context.has_origin,
            start_after_top=None,
        )
        if items:
            return items, previous_context.currency, previous_context

        if self._looks_like_table_continuation(rows):
            raise InvoiceParsingError(
                "Could not parse continuation page of the invoice table"
            )

        return [], previous_context.currency, previous_context

    def _validate_items(self, items: list[InvoiceLineItem]) -> None:
        line_numbers = [item.line_no for item in items]
        if len(line_numbers) != len(set(line_numbers)):
            raise InvoiceParsingError(
                "Invoice line numbers are duplicated; PDF generation aborted"
            )
        if line_numbers != sorted(line_numbers):
            raise InvoiceParsingError("Invoice line numbers are not strictly ascending")
        for item in items:
            if not item.item_name:
                raise InvoiceParsingError(
                    f"Invoice item name is empty for line {item.line_no}"
                )
            if not self._extract_hs_code(item.hs_code):
                raise InvoiceParsingError(
                    f"Invalid HS code for line {item.line_no}: {item.hs_code}"
                )
            for field_name in ("currency", "quantity", "unit_price", "line_value"):
                if not getattr(item, field_name):
                    raise InvoiceParsingError(
                        f"{field_name} is empty for line {item.line_no}"
                    )

    def _group_rows(self, words: list[dict[str, Any]]) -> list[_PhysicalRow]:
        ordered_words = sorted(words, key=lambda word: (word["top"], word["x0"]))
        rows: list[_PhysicalRow] = []
        for word in ordered_words:
            if not rows or abs(rows[-1].top - word["top"]) > self.ROW_TOLERANCE:
                rows.append(_PhysicalRow(top=float(word["top"]), words=[word]))
                continue
            rows[-1].words.append(word)

        for row in rows:
            row.words.sort(key=lambda word: word["x0"])
        return rows

    def _find_header_rows(self, rows: list[_PhysicalRow]) -> _HeaderContext | None:
        for index, row in enumerate(rows):
            text = collapse_whitespace(
                " ".join(word["text"] for word in row.words)
            ).lower()
            if all(token in text for token in self.HEADER_REQUIRED_TOKENS):
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
                return _HeaderContext(
                    rows=header_rows, has_origin="origin" in combined_header_text
                )
        return None

    def _build_columns(
        self,
        header_context: _HeaderContext,
        page_width: float,
    ) -> dict[str, tuple[float, float]]:
        words = [word for row in header_context.rows for word in row.words]
        word_by_text = [(word["text"].lower(), float(word["x0"])) for word in words]

        line_no_x = self._find_column_start(word_by_text, "lp")
        description_x = self._find_column_start(word_by_text, "description")
        hs_code_x = self._find_column_start(word_by_text, "hs")
        qty_x = self._find_column_start(word_by_text, "qty")
        line_value_x = self._find_column_start(word_by_text, "line")
        total_net_x = self._find_column_start(word_by_text, "total")

        origin_x = (
            self._find_column_start(word_by_text, "origin")
            if header_context.has_origin
            else qty_x
        )
        unit_candidates = sorted(x for text, x in word_by_text if text == "unit")
        unit_price_x = next(
            (x for x in unit_candidates if x > qty_x and x < line_value_x), None
        )
        unit_net_x = next((x for x in unit_candidates if x > line_value_x), None)

        if unit_price_x is None or unit_net_x is None:
            raise InvoiceParsingError("Could not determine PDF table column boundaries")

        columns = {
            "line_no": (max(0.0, line_no_x - 8), description_x - 2),
            "description": (description_x - 2, hs_code_x - 4),
            "hs_code": (
                hs_code_x - 4,
                (origin_x if header_context.has_origin else qty_x) - 4,
            ),
        }
        if header_context.has_origin:
            columns["origin"] = (origin_x - 4, qty_x - 4)
        columns.update(
            {
                "qty": (qty_x - 4, unit_price_x - 4),
                "unit_price": (unit_price_x - 4, line_value_x - 4),
                "line_value": (line_value_x - 4, unit_net_x - 4),
                "unit_net_weight": (unit_net_x - 4, total_net_x - 4),
                "total_net_weight": (total_net_x - 4, page_width),
            }
        )
        return columns

    def _collect_items_from_rows(
        self,
        rows: list[_PhysicalRow],
        *,
        columns: dict[str, tuple[float, float]],
        currency: str,
        has_origin: bool,
        start_after_top: float | None,
    ) -> list[InvoiceLineItem]:
        items: list[InvoiceLineItem] = []
        current_item: dict[str, str] | None = None
        start_collecting = False

        for row in rows:
            if start_after_top is not None and row.top <= start_after_top:
                continue

            cells = self._row_to_cells(row, columns)
            joined_text = " ".join(value for value in cells.values() if value)
            if not joined_text:
                continue

            if self._looks_like_end(joined_text):
                break

            has_new_item = bool(self.LINE_NUMBER_PATTERN.fullmatch(cells["line_no"]))
            current_row_hs_code = self._resolve_row_hs_code(cells, joined_text)
            has_hs_code = bool(current_row_hs_code)

            if has_new_item and self._looks_like_item_start(cells, joined_text):
                start_collecting = True
                if current_item is not None:
                    items.append(self._to_invoice_line_item(current_item))
                current_item = self._start_item_from_cells(
                    cells, joined_text, currency, has_origin
                )
                continue

            if not start_collecting or current_item is None:
                continue

            self._merge_row_into_item(current_item, cells, joined_text, has_origin)
            if has_hs_code and not cells["description"] and not cells["line_no"]:
                current_item["hs_code"] = current_row_hs_code

        if current_item is not None:
            items.append(self._to_invoice_line_item(current_item))

        return items

    def _detect_currency(
        self,
        header_rows: list[_PhysicalRow],
        rows: list[_PhysicalRow],
    ) -> str:
        for source_rows in (header_rows, rows):
            currencies = [
                word["text"].strip().upper()
                for row in source_rows
                for word in row.words
                if word["text"].strip().upper() in self.SUPPORTED_CURRENCIES
            ]
            if currencies:
                return currencies[0]
        raise InvoiceParsingError(
            "Could not determine invoice currency from the PDF table"
        )

    def _looks_like_end(self, line: str) -> bool:
        lower = line.lower()
        return any(keyword in lower for keyword in self.END_KEYWORDS)

    def _looks_like_table_continuation(self, rows: list[_PhysicalRow]) -> bool:
        for row in rows:
            row_text = collapse_whitespace(" ".join(word["text"] for word in row.words))
            if not row_text or self._looks_like_end(row_text):
                continue
            if self.HS_CODE_PATTERN.search(row_text):
                return True
            if self.LINE_NUMBER_PATTERN.search(
                row_text
            ) and self._row_contains_numeric_triplet(row_text):
                return True
        return False

    def _has_table_body_rows(
        self,
        rows: list[_PhysicalRow],
        columns: dict[str, tuple[float, float]],
    ) -> bool:
        for row in rows:
            cells = self._row_to_cells(row, columns)
            joined_text = " ".join(value for value in cells.values() if value)
            if not joined_text or self._looks_like_end(joined_text):
                continue
            if self._looks_like_item_start(cells, joined_text):
                return True
        return False

    def _find_column_start(self, words: list[tuple[str, float]], token: str) -> float:
        for text, x0 in words:
            if text == token:
                return x0
        raise InvoiceParsingError(
            f"Could not find '{token}' column in invoice PDF header"
        )

    def _row_to_cells(
        self,
        row: _PhysicalRow,
        columns: dict[str, tuple[float, float]],
    ) -> dict[str, str]:
        cells = {name: "" for name in columns}
        for word in row.words:
            midpoint = (float(word["x0"]) + float(word["x1"])) / 2
            for name, (left, right) in columns.items():
                if left <= midpoint < right:
                    cells[name] = self._append_token(cells[name], word["text"])
                    break
        return cells

    def _start_item_from_cells(
        self,
        cells: dict[str, str],
        joined_text: str,
        currency: str,
        has_origin: bool,
    ) -> dict[str, str]:
        return {
            "line_no": cells["line_no"],
            "item_name": cells["description"],
            "hs_code": self._resolve_row_hs_code(cells, joined_text),
            "origin": cells.get("origin", "") if has_origin else "",
            "currency": currency,
            "quantity": cells["qty"],
            "unit_price": cells["unit_price"],
            "line_value": cells["line_value"],
            "unit_net_weight_kg": cells["unit_net_weight"],
            "total_net_weight_kg": cells["total_net_weight"],
            "source_text": joined_text,
        }

    def _merge_row_into_item(
        self,
        current_item: dict[str, str],
        cells: dict[str, str],
        joined_text: str,
        has_origin: bool,
    ) -> None:
        if cells["description"]:
            current_item["item_name"] = collapse_whitespace(
                f'{current_item["item_name"]} {cells["description"]}'
            )
        current_item["source_text"] = collapse_whitespace(
            f'{current_item["source_text"]} {joined_text}'
        )

        keys = [
            ("hs_code", "hs_code"),
            ("qty", "quantity"),
            ("unit_price", "unit_price"),
            ("line_value", "line_value"),
            ("unit_net_weight", "unit_net_weight_kg"),
            ("total_net_weight", "total_net_weight_kg"),
        ]
        if has_origin:
            keys.insert(1, ("origin", "origin"))

        for source_key, target_key in keys:
            if cells.get(source_key) and not current_item[target_key]:
                if target_key == "hs_code":
                    normalized_hs_code = self._resolve_row_hs_code(cells, joined_text)
                    if normalized_hs_code:
                        current_item[target_key] = normalized_hs_code
                    continue
                current_item[target_key] = cells[source_key]

        if not current_item["hs_code"]:
            fallback_hs_code = self._resolve_row_hs_code(cells, joined_text)
            if fallback_hs_code:
                current_item["hs_code"] = fallback_hs_code

    def _to_invoice_line_item(self, raw_item: dict[str, str]) -> InvoiceLineItem:
        return InvoiceLineItem(
            line_no=int(raw_item["line_no"]),
            item_name=collapse_whitespace(raw_item["item_name"]),
            hs_code=collapse_whitespace(raw_item["hs_code"]),
            origin=collapse_whitespace(raw_item["origin"]) or None,
            currency=collapse_whitespace(raw_item["currency"]),
            quantity=collapse_whitespace(raw_item["quantity"]),
            unit_price=collapse_whitespace(raw_item["unit_price"]),
            line_value=collapse_whitespace(raw_item["line_value"]),
            unit_net_weight_kg=collapse_whitespace(raw_item["unit_net_weight_kg"])
            or "0",
            total_net_weight_kg=collapse_whitespace(raw_item["total_net_weight_kg"])
            or "0",
            source_text=collapse_whitespace(raw_item["source_text"]),
        )

    def _append_token(self, current: str, token: str) -> str:
        if not current:
            return token
        if token in {".", ",", ";", ":", ")", "]"}:
            return f"{current}{token}"
        if token in {"(", "["}:
            return f"{current} {token}"
        if current.endswith(("(", "[", "/")):
            return f"{current}{token}"
        return f"{current} {token}"

    def _extract_hs_code(self, value: str) -> str:
        match = self.HS_CODE_PATTERN.search(value or "")
        return match.group(0) if match else ""

    def _resolve_row_hs_code(self, cells: dict[str, str], joined_text: str) -> str:
        return self._extract_hs_code(cells.get("hs_code", "")) or self._extract_hs_code(
            joined_text
        )

    def _looks_like_item_start(self, cells: dict[str, str], joined_text: str) -> bool:
        if not self.LINE_NUMBER_PATTERN.fullmatch(cells["line_no"]):
            return False
        if self._resolve_row_hs_code(cells, joined_text):
            return True
        return (
            self._has_numeric_value(cells.get("qty", ""))
            and self._has_numeric_value(cells.get("unit_price", ""))
            and self._has_numeric_value(cells.get("line_value", ""))
        )

    def _row_contains_numeric_triplet(self, value: str) -> bool:
        matches = re.findall(r"\b\d+(?:[.,]\d+)?\b", value)
        return len(matches) >= 3

    def _has_numeric_value(self, value: str) -> bool:
        normalized = collapse_whitespace(value).replace(" ", "")
        return bool(re.fullmatch(r"\d+(?:[.,]\d+)?", normalized))
