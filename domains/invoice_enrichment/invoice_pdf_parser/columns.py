from __future__ import annotations

from domains.invoice_enrichment.invoice_pdf_parser.parsing_error import ParsingError
from domains.invoice_enrichment.invoice_pdf_parser.models import HeaderContext


class ColumnDetector:
    def build_columns(
        self,
        header_context: HeaderContext,
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
            raise ParsingError("Could not determine PDF table column boundaries")

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

    def _find_column_start(self, words: list[tuple[str, float]], token: str) -> float:
        for text, x0 in words:
            if text == token:
                return x0
        raise ParsingError(f"Could not find '{token}' column in invoice PDF header")
