from __future__ import annotations

import logging
from typing import Any

import fitz

from domains.invoice_enrichment.models import ProcessedInvoiceResult
from domains.invoice_enrichment.pdf_document.models import HeaderMetadata
from domains.invoice_enrichment.pdf_document.text import TextRenderer
from domains.invoice_enrichment.pdf_document.totals import display_currency


class LayoutRenderer:
    def __init__(
        self,
        text: TextRenderer,
        *,
        default_page_width: float,
        default_page_height: float,
        margin_x: float,
        margin_top: float,
        header_font_size: float,
        body_font_size: float,
        title_font_size: float,
        subtitle_font_size: float,
        line_height: float,
        row_padding: float,
        header_padding: float,
        base_columns: tuple,
    ) -> None:
        self._text = text
        self._default_page_width = default_page_width
        self._default_page_height = default_page_height
        self._margin_x = margin_x
        self._margin_top = margin_top
        self._header_font_size = header_font_size
        self._body_font_size = body_font_size
        self._title_font_size = title_font_size
        self._subtitle_font_size = subtitle_font_size
        self._line_height = line_height
        self._row_padding = row_padding
        self._header_padding = header_padding
        self._base_columns = base_columns

    def resolve_page_size(self, src_doc: fitz.Document | None) -> tuple[float, float]:
        if src_doc is not None:
            try:
                first_page = src_doc[0]
                return first_page.rect.width, first_page.rect.height
            except Exception as exc:
                logging.getLogger(__name__).debug(
                    "Could not read page size from source PDF: %s", exc
                )
        return self._default_page_width, self._default_page_height

    def build_columns(
        self,
        page_width: float,
        result: ProcessedInvoiceResult,
    ) -> tuple[tuple[str, str, float], ...]:
        available_width = page_width - (self._margin_x * 2)
        base_total = sum(width for _, _, width in self._base_columns)
        scale = available_width / base_total
        currency = display_currency(result)
        return tuple(
            (name, label.format(currency=currency), width * scale)
            for name, label, width in self._base_columns
        )

    def start_render_page(
        self,
        doc: fitz.Document,
        *,
        page_width: float,
        page_height: float,
        header_meta: HeaderMetadata,
        columns: tuple[tuple[str, str, float], ...],
        x_positions: list[float],
        header_height: float,
    ) -> tuple[fitz.Page, float]:
        page = doc.new_page(width=page_width, height=page_height)
        y = self._write_page_header(page, header_meta)
        y = self._draw_table_header(page, columns, x_positions, y, header_height)
        return page, y

    def build_x_positions(
        self, columns: tuple[tuple[str, str, float], ...]
    ) -> list[float]:
        positions = [self._margin_x]
        current = self._margin_x
        for _, _, width in columns:
            current += width
            positions.append(current)
        return positions

    def measure_header_height(
        self, columns: tuple[tuple[str, str, float], ...]
    ) -> float:
        max_lines = 1
        for _, label, width in columns:
            wrapped = self._text.wrap_cell_text(
                label, width - (self._header_padding * 2), self._header_font_size
            )
            max_lines = max(max_lines, len(wrapped))
        return max(32, max_lines * self._line_height + self._header_padding * 2 + 4)

    def row_values(self, description: Any) -> dict[str, str]:
        return {
            "line_no": str(description.line_no),
            "description": self._text.prepare_cell_text(
                f"PL: {description.description_pl}\nEN: {description.description_en}"
            ),
            "hs_code": self._text.prepare_cell_text(description.hs_code),
            "made_of": self._text.prepare_cell_text(description.made_of),
            "made_in": self._text.prepare_cell_text(description.made_in),
            "country_of_origin": self._text.prepare_cell_text(
                description.country_of_origin
            ),
            "melt_and_pour": self._text.prepare_cell_text(description.melt_and_pour),
            "manufacturer_data": self._text.prepare_cell_text(
                description.manufacturer_data
            ),
            "quantity": self._text.prepare_cell_text(description.quantity),
            "unit_price": self._text.prepare_cell_text(description.unit_price),
            "line_value": self._text.prepare_cell_text(description.line_value),
            "net_weight_kg": self._text.prepare_cell_text(description.net_weight_kg),
        }

    def measure_row_height(
        self,
        row_cells: dict[str, str],
        columns: tuple[tuple[str, str, float], ...],
    ) -> float:
        line_counts = []
        for column_name, _, width in columns:
            wrapped = self._text.wrap_cell_text(
                row_cells[column_name], width - 8, self._body_font_size
            )
            line_counts.append(max(1, len(wrapped)))
        return max(line_counts) * self._line_height + self._row_padding * 2 + 2

    def draw_row(
        self,
        page: fitz.Page,
        columns: tuple[tuple[str, str, float], ...],
        x_positions: list[float],
        y: float,
        row_height: float,
        row_cells: dict[str, str],
    ) -> None:
        for index, (column_name, _, _) in enumerate(columns):
            rect = fitz.Rect(
                x_positions[index], y, x_positions[index + 1], y + row_height
            )
            page.draw_rect(rect, color=(0.35, 0.35, 0.35), width=0.5)
            wrapped = self._text.wrap_cell_text(
                row_cells[column_name],
                rect.width - 8,
                self._body_font_size,
            )
            self._text.draw_multiline_text(
                page,
                rect,
                wrapped,
                font_size=self._body_font_size,
                padding=3,
            )

    def _write_page_header(
        self,
        page: fitz.Page,
        header_meta: HeaderMetadata,
    ) -> float:
        x = self._margin_x + 4
        y = self._margin_top + 18
        page.insert_text(
            fitz.Point(x, y),
            "Opis towarow / Goods Description",
            fontsize=self._title_font_size,
            fontname="helv",
            render_mode=0,
        )
        y += 18
        subtitle_label = (
            "Inter-Store Shift nr"
            if header_meta.document_type == "inter_store_shift"
            else "Invoice nr"
        )
        subtitle = f"{subtitle_label} {header_meta.invoice_ref}"
        page.insert_text(
            fitz.Point(x, y),
            subtitle,
            fontsize=self._subtitle_font_size,
            fontname="helv",
        )
        if header_meta.issue_date:
            y += 12
            page.insert_text(
                fitz.Point(x, y),
                f"Data wystawienia / Issue date: {header_meta.issue_date}",
                fontsize=self._subtitle_font_size,
                fontname="helv",
            )
        return y + 16

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
            page.draw_rect(
                rect, color=(0.25, 0.25, 0.25), fill=(0.86, 0.9, 0.97), width=0.6
            )
            lines = self._text.wrap_cell_text(
                label, rect.width - (self._header_padding * 2), self._header_font_size
            )
            self._text.draw_multiline_text(
                page,
                rect,
                lines,
                font_size=self._header_font_size,
                padding=self._header_padding,
            )
        return y + height
