from __future__ import annotations

import fitz

from domains.invoice_enrichment.goods_description.diagnostics import (
    Diagnostics,
)
from domains.invoice_enrichment.models import (
    ProcessedInvoiceResult,
    SourceInvoiceDocument,
)
from domains.invoice_enrichment.pdf_document.layout import LayoutRenderer
from domains.invoice_enrichment.pdf_document.text import TextRenderer
from domains.invoice_enrichment.pdf_document.totals import TotalsRenderer


class Builder:
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

    def __init__(self) -> None:
        text = TextRenderer(line_height=self.LINE_HEIGHT)
        self._totals = TotalsRenderer(
            margin_x=self.MARGIN_X,
            margin_bottom=self.MARGIN_BOTTOM,
        )
        self._layout = LayoutRenderer(
            text=text,
            default_page_width=self.DEFAULT_PAGE_WIDTH,
            default_page_height=self.DEFAULT_PAGE_HEIGHT,
            margin_x=self.MARGIN_X,
            margin_top=self.MARGIN_TOP,
            header_font_size=self.HEADER_FONT_SIZE,
            body_font_size=self.BODY_FONT_SIZE,
            title_font_size=self.TITLE_FONT_SIZE,
            subtitle_font_size=self.SUBTITLE_FONT_SIZE,
            line_height=self.LINE_HEIGHT,
            row_padding=self.ROW_PADDING,
            header_padding=self.HEADER_PADDING,
            base_columns=self.BASE_COLUMNS,
        )

    def build(
        self,
        source_document: SourceInvoiceDocument,
        parsed_document,
        descriptions,
        *,
        diagnostics: Diagnostics | None = None,
    ) -> tuple[ProcessedInvoiceResult, bytes]:
        result = ProcessedInvoiceResult(
            message="Invoice processed successfully",
            order_id=source_document.order_id,
            invoice_id=source_document.invoice_id,
            invoice_number=source_document.invoice_number,
            document_type=parsed_document.document_type,
            document_ref=parsed_document.document_ref,
            issue_date=parsed_document.issue_date,
            currency=parsed_document.currency
            or (
                parsed_document.line_items[0].currency
                if parsed_document.line_items
                else None
            ),
            source_filename=source_document.source_filename,
            original_pdf_size_bytes=len(source_document.pdf_bytes),
            line_items=parsed_document.line_items,
            descriptions=descriptions,
            enrichment_warnings=(
                diagnostics.warning_messages() if diagnostics is not None else []
            ),
            enrichment_diagnostics=(
                diagnostics.to_dicts() if diagnostics is not None else []
            ),
        )
        return result, self.render(result, source_pdf_bytes=source_document.pdf_bytes)

    def render(
        self, result: ProcessedInvoiceResult, *, source_pdf_bytes: bytes | None = None
    ) -> bytes:
        src_doc = (
            fitz.open(stream=source_pdf_bytes, filetype="pdf")
            if source_pdf_bytes
            else None
        )
        try:
            page_width, page_height = self._layout.resolve_page_size(src_doc)
            columns = self._layout.build_columns(page_width, result)
            header_meta = self._totals.resolve_header_metadata(result, src_doc)
        finally:
            if src_doc is not None:
                src_doc.close()

        x_positions = self._layout.build_x_positions(columns)
        header_height = self._layout.measure_header_height(columns)

        doc = fitz.open()
        page, y = self._layout.start_render_page(
            doc,
            page_width=page_width,
            page_height=page_height,
            header_meta=header_meta,
            columns=columns,
            x_positions=x_positions,
            header_height=header_height,
        )

        for description in result.descriptions:
            row_cells = self._layout.row_values(description)
            row_height = self._layout.measure_row_height(row_cells, columns)
            if y + row_height > page.rect.height - self.MARGIN_BOTTOM - 34:
                page, y = self._layout.start_render_page(
                    doc,
                    page_width=page_width,
                    page_height=page_height,
                    header_meta=header_meta,
                    columns=columns,
                    x_positions=x_positions,
                    header_height=header_height,
                )
            self._layout.draw_row(page, columns, x_positions, y, row_height, row_cells)
            y += row_height

        if y + 28 > page.rect.height - self.MARGIN_BOTTOM:
            page, y = self._layout.start_render_page(
                doc,
                page_width=page_width,
                page_height=page_height,
                header_meta=header_meta,
                columns=columns,
                x_positions=x_positions,
                header_height=header_height,
            )
        self._totals.draw_totals(page, result, y + 10)
        output = doc.tobytes()
        doc.close()
        return output
