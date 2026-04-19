from __future__ import annotations

import re

from core.utils import clean_optional_text, collapse_whitespace
from domains.invoice_enrichment.goods_description.rules import (
    ADDRESS_BANNED_ARTIFACTS,
    ADDRESS_STREET_HINTS,
    PLACEHOLDER_VALUES,
)


class AddressRules:
    def resolve(
        self,
        value: object,
        *,
        hint: str,
        invoice_origin: str | None,
        country_of_origin: str,
    ) -> str:
        raw = self.sanitize(clean_optional_text(value))
        if self.is_acceptable(
            raw, invoice_origin=invoice_origin, country_of_origin=country_of_origin
        ):
            return raw
        hint = self.sanitize(hint)
        if self.is_acceptable(
            hint, invoice_origin=invoice_origin, country_of_origin=country_of_origin
        ):
            return hint
        return raw or hint

    def is_full_address(self, value: str) -> bool:
        cleaned = self.sanitize(value)
        if self._is_placeholder(cleaned):
            return False
        if self.contains_artifacts(cleaned):
            return False
        parts = [part.strip() for part in cleaned.split(",") if part.strip()]
        if len(parts) < 4:
            return False
        country_part = parts[-1]
        locality_part = parts[-2]
        street_parts = parts[1:-1]
        street_text = " ".join(street_parts).lower()
        if any(char.isdigit() for char in country_part):
            return False
        if not re.search(r"\d", locality_part):
            return False
        if not re.search(r"\d", street_text) and not any(
            hint in street_text for hint in ADDRESS_STREET_HINTS
        ):
            return False
        return True

    def mentions_china(self, value: str) -> bool:
        lowered = self.sanitize(value).lower()
        return " china" in f" {lowered}" or lowered.endswith("china")

    def is_acceptable(
        self,
        value: str,
        *,
        invoice_origin: str | None,
        country_of_origin: str,
    ) -> bool:
        if not self.is_full_address(value):
            return False
        if self.mentions_china(value) and (
            clean_optional_text(invoice_origin).upper() == "CN"
            or country_of_origin != "China"
        ):
            return False
        return True

    def sanitize(self, value: str) -> str:
        cleaned = value.strip()
        cleaned = re.split(r"\s*\(\[", cleaned, maxsplit=1)[0]
        cleaned = collapse_whitespace(cleaned)
        return cleaned.strip(" ,;.")

    def contains_artifacts(self, value: str) -> bool:
        lowered = self.sanitize(value).lower()
        if not lowered:
            return False
        if any(token in lowered for token in ADDRESS_BANNED_ARTIFACTS):
            return True
        if re.search(r"\b\S+@\S+\b", lowered):
            return True
        if re.search(r"\b[a-z0-9._-]+@[a-z0-9._-]+\b", lowered):
            return True
        return False

    def _is_placeholder(self, value: str | None) -> bool:
        if value is None:
            return True
        return collapse_whitespace(str(value)).upper() in PLACEHOLDER_VALUES
