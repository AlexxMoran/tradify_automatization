from __future__ import annotations

import re
from typing import Pattern

from core.utils import collapse_whitespace
from domains.invoice_enrichment.invoice_pdf_parser.models import PhysicalRow
from domains.invoice_enrichment.models import InvoiceLineItem


class ItemCollector:
    def __init__(
        self,
        line_number_pattern: Pattern[str],
        hs_code_pattern: Pattern[str],
        end_keywords: tuple[str, ...],
    ) -> None:
        self._line_number_pattern = line_number_pattern
        self._hs_code_pattern = hs_code_pattern
        self._end_keywords = end_keywords

    def collect_items_from_rows(
        self,
        rows: list[PhysicalRow],
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

            cells = self.row_to_cells(row, columns)
            joined_text = " ".join(value for value in cells.values() if value)
            if not joined_text:
                continue

            if self.looks_like_end(joined_text):
                break

            has_new_item = bool(self._line_number_pattern.fullmatch(cells["line_no"]))
            current_row_hs_code = self._resolve_row_hs_code(cells, joined_text)
            has_hs_code = bool(current_row_hs_code)

            if has_new_item and self.looks_like_item_start(cells, joined_text):
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

    def row_to_cells(
        self,
        row: PhysicalRow,
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

    def looks_like_end(self, line: str) -> bool:
        lower = line.lower()
        return any(keyword in lower for keyword in self._end_keywords)

    def looks_like_item_start(self, cells: dict[str, str], joined_text: str) -> bool:
        if not self._line_number_pattern.fullmatch(cells["line_no"]):
            return False
        if self._resolve_row_hs_code(cells, joined_text):
            return True
        return (
            self._has_numeric_value(cells.get("qty", ""))
            and self._has_numeric_value(cells.get("unit_price", ""))
            and self._has_numeric_value(cells.get("line_value", ""))
        )

    def extract_hs_code(self, value: str) -> str:
        match = self._hs_code_pattern.search(value or "")
        return match.group(0) if match else ""

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

    def _resolve_row_hs_code(self, cells: dict[str, str], joined_text: str) -> str:
        return self.extract_hs_code(cells.get("hs_code", "")) or self.extract_hs_code(
            joined_text
        )

    def _row_contains_numeric_triplet(self, value: str) -> bool:
        matches = re.findall(r"\b\d+(?:[.,]\d+)?\b", value)
        return len(matches) >= 3

    def _has_numeric_value(self, value: str) -> bool:
        normalized = collapse_whitespace(value).replace(" ", "")
        return bool(re.fullmatch(r"\d+(?:[.,]\d+)?", normalized))
