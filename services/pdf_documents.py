from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from decimal import Decimal, InvalidOperation
from pathlib import Path

import fitz
from pypdf import PdfReader, PdfWriter

from models import ProcessedInvoiceResult


class PdfDocumentError(Exception):
    pass


@dataclass(slots=True)
class _HeaderMetadata:
    invoice_ref: str
    issue_date: str | None = None


class GoodsDescriptionPdfBuilder:
    DEFAULT_PAGE_WIDTH = 595
    DEFAULT_PAGE_HEIGHT = 842
    MARGIN_X = 24
    MARGIN_TOP = 28
    MARGIN_BOTTOM = 28
    HEADER_FONT_SIZE = 5.8
    BODY_FONT_SIZE = 5.5
    TITLE_FONT_SIZE = 16
    SUBTITLE_FONT_SIZE = 10
    LINE_HEIGHT = 6.6
    ROW_PADDING = 3
    HEADER_PADDING = 5
    BASE_COLUMNS = (
        ("line_no", "L.P.", 16),
        ("description", "Product EN/PL (what it is & use)", 162),
        ("hs_code", "HS Code", 50),
        ("made_of", "Made of", 40),
        ("made_in", "Made in", 38),
        ("country_of_origin", "Country\nof origin", 40),
        ("melt_and_pour", "Melt &\nPour", 33),
        ("manufacturer_data", "Manufacturer's data\n(address)", 96),
        ("quantity", "Qty", 32),
        ("unit_price", "Unit\nprice\n({currency})", 34),
        ("line_value", "Line\nvalue\n({currency})", 34),
        ("net_weight_kg", "Net\nweight\n(kg)", 32),
    )
    COMMERCIAL_INVOICE_PATTERN = re.compile(
        r"Commercial\s+Invoice\s+nr\s+([A-Z0-9]+(?:[/-][A-Z0-9]+)+)",
        re.IGNORECASE,
    )
    ISSUE_DATE_PATTERN = re.compile(
        r"(?:Data\s+wystawienia|Issue\s+date)(?:\s*/\s*Issue\s+date)?\s*:\s*(\d{4}-\d{2}-\d{2})",
        re.IGNORECASE,
    )

    def build(self, invoice_file, line_items, descriptions) -> tuple[ProcessedInvoiceResult, bytes]:
        result = ProcessedInvoiceResult(
            message="Invoice processed successfully",
            order_id=invoice_file.order_id,
            invoice_id=invoice_file.invoice_id,
            invoice_number=invoice_file.invoice_number,
            currency=line_items[0].currency if line_items else None,
            source_filename=(
                invoice_file.invoice_number or f"invoice_{invoice_file.order_id}.pdf"
            ),
            original_pdf_size_bytes=len(invoice_file.pdf_bytes),
            line_items=line_items,
            descriptions=descriptions,
        )
        return result, self.render(result, source_pdf_bytes=invoice_file.pdf_bytes)

    def render(self, result: ProcessedInvoiceResult, *, source_pdf_bytes: bytes | None = None) -> bytes:
        src_doc = fitz.open(stream=source_pdf_bytes, filetype="pdf") if source_pdf_bytes else None
        try:
            page_width, page_height = self._resolve_page_size(src_doc)
            columns = self._build_columns(page_width, result)
            header_meta = self._resolve_header_metadata(result, src_doc)
        finally:
            if src_doc is not None:
                src_doc.close()
        x_positions = self._build_x_positions(columns)
        header_height = self._measure_header_height(columns)

        doc = fitz.open()
        page, y = self._start_render_page(
            doc,
            page_width=page_width,
            page_height=page_height,
            header_meta=header_meta,
            columns=columns,
            x_positions=x_positions,
            header_height=header_height,
        )

        for description in result.descriptions:
            row_cells = self._row_values(description)
            row_height = self._measure_row_height(row_cells, columns)
            if y + row_height > page.rect.height - self.MARGIN_BOTTOM - 34:
                page, y = self._start_render_page(
                    doc,
                    page_width=page_width,
                    page_height=page_height,
                    header_meta=header_meta,
                    columns=columns,
                    x_positions=x_positions,
                    header_height=header_height,
                )
            self._draw_row(page, columns, x_positions, y, row_height, row_cells)
            y += row_height

        if y + 28 > page.rect.height - self.MARGIN_BOTTOM:
            page, y = self._start_render_page(
                doc,
                page_width=page_width,
                page_height=page_height,
                header_meta=header_meta,
                columns=columns,
                x_positions=x_positions,
                header_height=header_height,
            )
        self._draw_totals(page, result, y + 10)
        output = doc.tobytes()
        doc.close()
        return output

    def _new_page(self, doc: fitz.Document, page_width: float, page_height: float) -> fitz.Page:
        return doc.new_page(width=page_width, height=page_height)

    def _start_render_page(
        self,
        doc: fitz.Document,
        *,
        page_width: float,
        page_height: float,
        header_meta: _HeaderMetadata,
        columns: tuple[tuple[str, str, float], ...],
        x_positions: list[float],
        header_height: float,
    ) -> tuple[fitz.Page, float]:
        page = self._new_page(doc, page_width, page_height)
        y = self._write_page_header(page, header_meta)
        y = self._draw_table_header(page, columns, x_positions, y, header_height)
        return page, y

    def _resolve_page_size(self, src_doc: fitz.Document | None) -> tuple[float, float]:
        if src_doc is not None:
            try:
                first_page = src_doc[0]
                return first_page.rect.width, first_page.rect.height
            except Exception as exc:
                import logging
                logging.getLogger(__name__).debug("Could not read page size from source PDF: %s", exc)
        return self.DEFAULT_PAGE_WIDTH, self.DEFAULT_PAGE_HEIGHT

    def _build_columns(
        self,
        page_width: float,
        result: ProcessedInvoiceResult,
    ) -> tuple[tuple[str, str, float], ...]:
        available_width = page_width - (self.MARGIN_X * 2)
        base_total = sum(width for _, _, width in self.BASE_COLUMNS)
        scale = available_width / base_total
        currency = self._display_currency(result)
        return tuple(
            (name, label.format(currency=currency), width * scale)
            for name, label, width in self.BASE_COLUMNS
        )

    def _write_page_header(
        self,
        page: fitz.Page,
        header_meta: _HeaderMetadata,
    ) -> float:
        x = self.MARGIN_X + 4
        y = self.MARGIN_TOP + 18
        page.insert_text(
            fitz.Point(x, y),
            "Opis towarow / Goods Description",
            fontsize=self.TITLE_FONT_SIZE,
            fontname="helv",
            render_mode=0,
        )
        y += 18
        subtitle = f"Invoice nr {header_meta.invoice_ref}"
        page.insert_text(
            fitz.Point(x, y),
            subtitle,
            fontsize=self.SUBTITLE_FONT_SIZE,
            fontname="helv",
        )
        if header_meta.issue_date:
            y += 12
            page.insert_text(
                fitz.Point(x, y),
                f"Data wystawienia / Issue date: {header_meta.issue_date}",
                fontsize=self.SUBTITLE_FONT_SIZE,
                fontname="helv",
            )
        return y + 16

    def _build_x_positions(self, columns: tuple[tuple[str, str, float], ...]) -> list[float]:
        positions = [self.MARGIN_X]
        current = self.MARGIN_X
        for _, _, width in columns:
            current += width
            positions.append(current)
        return positions

    def _measure_header_height(self, columns: tuple[tuple[str, str, float], ...]) -> float:
        max_lines = 1
        for _, label, width in columns:
            wrapped = self._wrap_cell_text(label, width - (self.HEADER_PADDING * 2), self.HEADER_FONT_SIZE)
            max_lines = max(max_lines, len(wrapped))
        return max(32, max_lines * self.LINE_HEIGHT + self.HEADER_PADDING * 2 + 4)

    def _draw_table_header(
        self,
        page: fitz.Page,
        columns: tuple[tuple[str, str, float], ...],
        x_positions: list[float],
        y: float,
        height: float,
    ) -> float:
        for index, (_, label, _) in enumerate(columns):
            rect = fitz.Rect(x_positions[index], y, x_positions[index + 1], y + height)
            page.draw_rect(rect, color=(0.25, 0.25, 0.25), fill=(0.86, 0.9, 0.97), width=0.6)
            lines = self._wrap_cell_text(label, rect.width - (self.HEADER_PADDING * 2), self.HEADER_FONT_SIZE)
            self._draw_multiline_text(
                page,
                rect,
                lines,
                font_size=self.HEADER_FONT_SIZE,
                padding=self.HEADER_PADDING,
            )
        return y + height

    def _row_values(self, description) -> dict[str, str]:
        return {
            "line_no": str(description.line_no),
            "description": (
                f"PL: {description.description_pl}\n"
                f"EN: {description.description_en}"
            ),
            "hs_code": description.hs_code,
            "made_of": description.made_of,
            "made_in": description.made_in,
            "country_of_origin": description.country_of_origin,
            "melt_and_pour": description.melt_and_pour,
            "manufacturer_data": description.manufacturer_data,
            "quantity": description.quantity,
            "unit_price": description.unit_price,
            "line_value": description.line_value,
            "net_weight_kg": description.net_weight_kg,
        }

    def _measure_row_height(
        self,
        row_cells: dict[str, str],
        columns: tuple[tuple[str, str, float], ...],
    ) -> float:
        line_counts = []
        for column_name, _, width in columns:
            wrapped = self._wrap_cell_text(row_cells[column_name], width - 6, self.BODY_FONT_SIZE)
            line_counts.append(max(1, len(wrapped)))
        return max(line_counts) * self.LINE_HEIGHT + self.ROW_PADDING * 2

    def _draw_row(
        self,
        page: fitz.Page,
        columns: tuple[tuple[str, str, float], ...],
        x_positions: list[float],
        y: float,
        row_height: float,
        row_cells: dict[str, str],
    ) -> None:
        for index, (column_name, _, _) in enumerate(columns):
            rect = fitz.Rect(x_positions[index], y, x_positions[index + 1], y + row_height)
            page.draw_rect(rect, color=(0.35, 0.35, 0.35), width=0.5)
            wrapped = self._wrap_cell_text(
                row_cells[column_name],
                rect.width - 6,
                self.BODY_FONT_SIZE,
            )
            self._draw_multiline_text(
                page,
                rect,
                wrapped,
                font_size=self.BODY_FONT_SIZE,
                padding=3,
            )

    def _wrap_cell_text(self, value: str, width: float, font_size: float) -> list[str]:
        normalized = value.strip()
        if not normalized:
            return [""]

        wrapped_lines: list[str] = []
        for raw_line in normalized.splitlines():
            line = raw_line.strip()
            if not line:
                wrapped_lines.append("")
                continue
            wrapped_lines.extend(self._wrap_line(line, width, font_size))
        return wrapped_lines or [normalized]

    def _wrap_line(self, line: str, width: float, font_size: float) -> list[str]:
        words = line.split()
        if not words:
            return [""]

        lines: list[str] = []
        current = ""
        for word in words:
            if not current:
                if self._fits_width(word, width, font_size):
                    current = word
                    continue
                broken_parts = self._break_long_token(word, width, font_size)
                lines.extend(broken_parts[:-1])
                current = broken_parts[-1]
                continue

            candidate = f"{current} {word}"
            if self._fits_width(candidate, width, font_size):
                current = candidate
                continue

            lines.append(current)
            if self._fits_width(word, width, font_size):
                current = word
                continue

            broken_parts = self._break_long_token(word, width, font_size)
            lines.extend(broken_parts[:-1])
            current = broken_parts[-1]

        if current:
            lines.append(current)
        return lines

    def _break_long_token(self, token: str, width: float, font_size: float) -> list[str]:
        if re.search(r"[/\-]", token):
            parts = self._break_token_by_delimiter(token, width, font_size)
            if parts:
                return parts
        return self._break_token_by_char(token, width, font_size)

    def _break_token_by_delimiter(self, token: str, width: float, font_size: float) -> list[str]:
        parts = re.split(r"([/\-])", token)
        if len(parts) <= 1:
            return []

        lines: list[str] = []
        current = ""
        index = 0
        while index < len(parts):
            piece = parts[index]
            if not piece:
                index += 1
                continue

            if index + 1 < len(parts) and parts[index + 1] in {"/", "-"}:
                piece = f"{piece}{parts[index + 1]}"
                index += 1

            candidate = f"{current}{piece}"
            if current and self._fits_width(candidate, width, font_size):
                current = candidate
            elif not current and self._fits_width(piece, width, font_size):
                current = piece
            else:
                if current:
                    lines.append(current)
                if self._fits_width(piece, width, font_size):
                    current = piece
                else:
                    char_parts = self._break_token_by_char(piece, width, font_size)
                    lines.extend(char_parts[:-1])
                    current = char_parts[-1]
            index += 1

        if current:
            lines.append(current)
        return lines

    def _break_token_by_char(self, token: str, width: float, font_size: float) -> list[str]:
        chunks: list[str] = []
        current = ""
        for char in token:
            candidate = f"{current}{char}"
            if current and not self._fits_width(candidate, width, font_size):
                chunks.append(current)
                current = char
                continue
            current = candidate
        if current:
            chunks.append(current)
        return chunks or [token]

    def _fits_width(self, value: str, width: float, font_size: float) -> bool:
        return fitz.get_text_length(value, fontname="helv", fontsize=font_size) <= width

    def _draw_multiline_text(
        self,
        page: fitz.Page,
        rect: fitz.Rect,
        lines: list[str],
        *,
        font_size: float,
        padding: float,
    ) -> None:
        x = rect.x0 + padding
        y = rect.y0 + padding + font_size
        for line in lines:
            if y > rect.y1 - padding:
                break
            page.insert_text(
                fitz.Point(x, y),
                line,
                fontsize=font_size,
                fontname="helv",
            )
            y += self.LINE_HEIGHT

    def _draw_totals(
        self,
        page: fitz.Page,
        result: ProcessedInvoiceResult,
        y: float,
    ) -> None:
        total_qty = self._sum_decimal(entry.quantity for entry in result.descriptions)
        total_value = self._sum_decimal(entry.line_value for entry in result.descriptions)
        currency = self._display_currency(result)
        start_y = min(y, page.rect.height - self.MARGIN_BOTTOM - 28)
        start_x = self.MARGIN_X
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

    def _sum_decimal(self, values) -> str:
        total = Decimal("0")
        for value in values:
            normalized = value.replace(" ", "").replace(",", ".")
            try:
                total += Decimal(normalized)
            except (InvalidOperation, AttributeError):
                continue
        if total == total.to_integral():
            return str(total.quantize(Decimal("1")))
        return f"{total:.2f}"

    def _display_invoice_ref(self, result: ProcessedInvoiceResult) -> str:
        if result.invoice_number:
            return result.invoice_number
        if result.source_filename:
            return Path(result.source_filename).stem
        return result.order_id

    def _resolve_header_metadata(
        self,
        result: ProcessedInvoiceResult,
        src_doc: fitz.Document | None,
    ) -> _HeaderMetadata:
        invoice_ref = result.invoice_number
        issue_date = None

        if src_doc is not None:
            parsed_ref, parsed_issue_date = self._extract_pdf_metadata(src_doc)
            invoice_ref = parsed_ref or invoice_ref
            issue_date = parsed_issue_date

        if not invoice_ref:
            invoice_ref = self._display_invoice_ref(result)

        return _HeaderMetadata(invoice_ref=invoice_ref, issue_date=issue_date)

    def _extract_pdf_metadata(self, src_doc: fitz.Document) -> tuple[str | None, str | None]:
        try:
            text = src_doc[0].get_text("text")
        except Exception:
            return None, None

        invoice_ref = self._extract_invoice_ref(text)
        issue_date_match = self.ISSUE_DATE_PATTERN.search(text)
        issue_date = issue_date_match.group(1).strip() if issue_date_match else None
        return invoice_ref, issue_date

    def _extract_invoice_ref(self, text: str) -> str | None:
        match = self.COMMERCIAL_INVOICE_PATTERN.search(text)
        if not match:
            return None
        return match.group(1).strip()

    def _display_currency(self, result: ProcessedInvoiceResult) -> str:
        if result.currency:
            return result.currency
        if result.descriptions:
            return result.descriptions[0].currency
        if result.line_items:
            return result.line_items[0].currency
        return "CUR"

    def _format_total_value(self, value: str, currency: str) -> str:
        if currency in {"EUR", "PLN"}:
            return value.replace(".", ",")
        return value


class PdfMergeService:
    def merge(self, result: ProcessedInvoiceResult, original_pdf_bytes: bytes, description_pdf_bytes: bytes) -> ProcessedInvoiceResult:
        try:
            writer = PdfWriter()
            writer.append(PdfReader(BytesIO(original_pdf_bytes)))
            writer.append(PdfReader(BytesIO(description_pdf_bytes)))
            buffer = BytesIO()
            writer.write(buffer)
        except Exception as exc:
            raise PdfDocumentError(f"Failed to merge invoice PDF documents: {exc}") from exc
        merged = buffer.getvalue()
        result.description_pdf_size_bytes = len(description_pdf_bytes)
        result.merged_pdf_size_bytes = len(merged)
        result.merged_pdf_bytes = merged
        return result
