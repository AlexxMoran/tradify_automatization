from __future__ import annotations

import re

from core.utils import clean_optional_text, collapse_whitespace
from domains.invoice_enrichment.goods_description.rules import (
    ALLOWED_MATERIALS,
    BANNED_MATERIAL_COMBINATIONS,
    BANNED_WORDS,
    PLACEHOLDER_VALUES,
)
from domains.invoice_enrichment.models import InvoiceLineItem


class MaterialRules:
    METAL_HINTS = (
        "metal",
        "steel",
        "stainless",
        "iron",
        "alloy",
        "zinc",
        "tin",
        "nickel",
        "chrome",
        "cast",
    )
    NON_METAL_HINTS = (
        "plastic",
        "polymer",
        "pp",
        "pe",
        "pvc",
        "vinyl",
        "abs",
        "resin",
        "rubber",
        "latex",
        "silicone",
        "silicon",
        "tyre",
        "tire",
        "tube",
        "detka",
        "textile",
        "fabric",
        "cotton",
        "polyester",
        "nylon",
        "felt",
        "wool",
        "thread",
        "ribbon",
        "patch",
        "lace",
        "yarn",
        "paper",
        "cardboard",
        "card",
        "puzzle",
        "board game",
        "gra planszowa",
        "wood",
        "wooden",
        "bamboo",
    )

    def contains_banned_words(self, value: str) -> bool:
        lowered = value.lower()
        if any(word in lowered.split() for word in BANNED_WORDS):
            return True
        if any(marker in lowered for marker in BANNED_MATERIAL_COMBINATIONS):
            return True
        return value not in ALLOWED_MATERIALS

    def resolve(self, value: object, *, hint: str, item: InvoiceLineItem) -> str:
        raw = clean_optional_text(value)
        if self._is_placeholder(raw):
            raw = hint
        raw = self.normalize(raw)
        if self.looks_fully_metal(
            collapse_whitespace(f"{item.item_name} {item.source_text}").lower()
        ):
            return "Steel"
        if raw:
            return raw
        hint_material = self.normalize(hint)
        if hint_material:
            return hint_material
        return self.fallback(item)

    def fallback(self, item: InvoiceLineItem) -> str:
        text = collapse_whitespace(f"{item.item_name} {item.source_text}").lower()
        if self.looks_fully_metal(text):
            return "Steel"
        if any(word in text for word in ("rubber", "tyre", "tire", "tube", "detka")):
            return "Rubber"
        if any(
            word in text
            for word in (
                "textile",
                "fabric",
                "thread",
                "ribbon",
                "patch",
                "felt",
                "yarn",
            )
        ):
            return "Textile"
        if any(word in text for word in ("puzzle", "board game", "gra planszowa")):
            return "Composite"
        return "Plastic"

    def normalize(self, value: str) -> str:
        cleaned = clean_optional_text(value)
        if self._is_placeholder(cleaned):
            return ""
        cleaned = re.sub(r"[(){}\[\]]", " ", cleaned)
        cleaned = cleaned.replace("&", " and ")
        if any(marker in cleaned.lower() for marker in BANNED_MATERIAL_COMBINATIONS):
            return ""
        return self._normalize_token(cleaned)

    def is_fully_metal_material(self, value: str) -> bool:
        return collapse_whitespace(value) == "Steel"

    def looks_fully_metal(self, text: str) -> bool:
        normalized = collapse_whitespace(text).lower()
        if not normalized:
            return False
        if not any(hint in normalized for hint in self.METAL_HINTS):
            return False
        return not any(hint in normalized for hint in self.NON_METAL_HINTS)

    def _normalize_token(self, value: str) -> str:
        token = collapse_whitespace(value)
        token = re.sub(r"[^A-Za-z0-9 -]", " ", token)
        token = collapse_whitespace(token)
        if not token:
            return ""
        lowered = token.lower()
        if self.looks_fully_metal(lowered):
            return "Steel"
        if any(word in lowered.split() for word in BANNED_WORDS):
            return ""
        if any(marker in lowered for marker in BANNED_MATERIAL_COMBINATIONS):
            return ""
        if any(
            word in lowered
            for word in (
                "rubber",
                "latex",
                "silicone",
                "silicon",
                "tyre",
                "tire",
                "tube",
                "detka",
            )
        ):
            return "Rubber"
        if any(
            word in lowered
            for word in (
                "textile",
                "fabric",
                "cotton",
                "polyester",
                "nylon",
                "felt",
                "wool",
                "thread",
                "ribbon",
                "patch",
                "lace",
                "yarn",
            )
        ):
            return "Textile"
        if any(
            word in lowered
            for word in (
                "composite",
                "paper",
                "cardboard",
                "card",
                "puzzle",
                "board game",
                "gra planszowa",
            )
        ):
            return "Composite"
        if any(
            word in lowered
            for word in (
                "plastic",
                "polymer",
                "pp",
                "pe",
                "pvc",
                "vinyl",
                "abs",
                "resin",
            )
        ):
            return "Plastic"
        return "Plastic"

    def _is_placeholder(self, value: str | None) -> bool:
        if value is None:
            return True
        return collapse_whitespace(str(value)).upper() in PLACEHOLDER_VALUES
