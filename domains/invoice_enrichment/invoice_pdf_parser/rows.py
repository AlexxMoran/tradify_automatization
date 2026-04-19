from __future__ import annotations

from typing import Any

from domains.invoice_enrichment.invoice_pdf_parser.models import PhysicalRow


class RowGrouper:
    def __init__(self, row_tolerance: float) -> None:
        self._row_tolerance = row_tolerance

    def group_rows(self, words: list[dict[str, Any]]) -> list[PhysicalRow]:
        ordered_words = sorted(words, key=lambda word: (word["top"], word["x0"]))
        rows: list[PhysicalRow] = []
        for word in ordered_words:
            if not rows or abs(rows[-1].top - word["top"]) > self._row_tolerance:
                rows.append(PhysicalRow(top=float(word["top"]), words=[word]))
                continue
            rows[-1].words.append(word)

        for row in rows:
            row.words.sort(key=lambda word: word["x0"])
        return rows
