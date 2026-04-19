from __future__ import annotations

from core.utils import clean_optional_text, collapse_whitespace
from domains.invoice_enrichment.goods_description.rules import (
    CHINA_ORIGIN_FALLBACK,
    COUNTRY_MAP,
    PLACEHOLDER_VALUES,
)
from domains.invoice_enrichment.models import ResolvedRuleHints


class CountryRules:
    def resolve(self, value: object, *, hint: str, invoice_origin: str | None) -> str:
        raw = clean_optional_text(value)
        if self._is_placeholder(raw):
            raw = hint
        if self._is_placeholder(raw):
            raw = self.fallback(invoice_origin, None)
        raw = clean_optional_text(raw)
        normalized = COUNTRY_MAP.get(raw.upper(), raw)
        if normalized == "China" and (
            clean_optional_text(invoice_origin).upper() == "CN"
            or (hint and hint != "China")
        ):
            if hint and hint != "China":
                normalized = hint
            else:
                normalized = CHINA_ORIGIN_FALLBACK
        return collapse_whitespace(normalized)

    def fallback(
        self, invoice_origin: str | None, hints: ResolvedRuleHints | None
    ) -> str:
        if hints and hints.country_of_origin_hint:
            return hints.country_of_origin_hint
        if not invoice_origin:
            return ""
        normalized = collapse_whitespace(invoice_origin).upper()
        mapped = COUNTRY_MAP.get(normalized, collapse_whitespace(invoice_origin))
        if mapped == "China":
            return CHINA_ORIGIN_FALLBACK
        return mapped

    def _is_placeholder(self, value: str | None) -> bool:
        if value is None:
            return True
        return collapse_whitespace(str(value)).upper() in PLACEHOLDER_VALUES
