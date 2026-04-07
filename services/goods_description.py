from __future__ import annotations

import json
import re
from typing import Any

from rules.goods_description_prompt import build_goods_description_prompt
from rules.goods_description_rules import (
    BANNED_WORDS,
    COUNTRY_MAP,
    MANUFACTURER_RULES,
)
from core.config import get_settings
from core.utils import clean_optional_text, collapse_whitespace
from models import GoodsDescriptionEntry, InvoiceLineItem


class DescriptionGenerationError(Exception):
    pass


class GoodsDescriptionGenerator:
    METAL_HINTS = (
        "metal",
        "steel",
        "stainless",
        "iron",
        "brass",
        "zinc",
        "alloy",
        "tin",
        "nickel",
        "chrome",
    )

    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = settings.openai_api_key
        self.model = settings.openai_model
        self.mode = settings.description_generation_mode.lower().strip() or "hybrid"
        self._openai_client = None
        if self.api_key:
            from openai import AsyncOpenAI
            self._openai_client = AsyncOpenAI(api_key=self.api_key)

    async def generate(
        self,
        line_items: list[InvoiceLineItem],
    ) -> list[GoodsDescriptionEntry]:
        if self.mode != "hybrid":
            raise DescriptionGenerationError("DESCRIPTION_GENERATION_MODE must be set to 'hybrid'")
        if not self.api_key or not self._openai_client:
            raise DescriptionGenerationError(
                "OPENAI_API_KEY is required when DESCRIPTION_GENERATION_MODE=hybrid"
            )

        try:
            descriptions = await self._generate_with_openai(line_items)
        except Exception as exc:
            raise DescriptionGenerationError(
                f"OpenAI description generation failed: {exc}"
            ) from exc

        self._validate_descriptions(line_items, descriptions)
        return descriptions

    async def _generate_with_openai(
        self,
        line_items: list[InvoiceLineItem],
    ) -> list[GoodsDescriptionEntry]:
        payload = [self._build_openai_payload_item(item) for item in line_items]

        response = await self._openai_client.responses.create(
            model=self.model,
            tools=[{"type": "web_search"}],
            tool_choice="required",
            input=build_goods_description_prompt(payload),
        )
        data = json.loads(response.output_text)
        items = data.get("items")
        if not isinstance(items, list):
            raise DescriptionGenerationError("OpenAI response does not contain a valid items array")

        descriptions: list[GoodsDescriptionEntry] = []
        source_by_line = {item.line_no: item for item in line_items}
        for entry in items:
            line_no = int(entry["line_no"])
            source_item = source_by_line.get(line_no)
            if source_item is None:
                raise DescriptionGenerationError(f"OpenAI returned an unknown line number: {line_no}")
            country_fallback = self._openai_country_fallback(source_item.origin)
            made_in = clean_optional_text(
                entry.get("made_in"),
                fallback=country_fallback,
            )
            country_of_origin = clean_optional_text(
                entry.get("country_of_origin"),
                fallback=country_fallback,
            )
            normalized_made_of = self._normalize_material_field(entry.get("made_of"))
            normalized_made_in = self._normalize_openai_country_field(made_in, country_fallback)
            normalized_country_of_origin = self._normalize_openai_country_field(
                country_of_origin,
                country_fallback,
            )
            descriptions.append(
                self._build_description_entry(
                    source_item,
                    description_en=self._sanitize_description(str(entry["description_en"])),
                    description_pl=self._sanitize_description(str(entry["description_pl"])),
                    made_of=normalized_made_of,
                    made_in=normalized_made_in,
                    country_of_origin=normalized_country_of_origin,
                    melt_and_pour=self._derive_melt_and_pour(
                        normalized_made_of,
                        normalized_made_in,
                        normalized_country_of_origin,
                    ),
                    manufacturer_data=self._normalize_manufacturer_data(
                        entry.get("manufacturer_data"),
                    ),
                )
            )
        return descriptions

    def _validate_descriptions(
        self,
        line_items: list[InvoiceLineItem],
        descriptions: list[GoodsDescriptionEntry],
    ) -> None:
        if len(line_items) != len(descriptions):
            raise DescriptionGenerationError(
                "Description count does not match invoice line count; PDF generation aborted"
            )

        expected_lines = [item.line_no for item in line_items]
        actual_lines = [item.line_no for item in descriptions]
        if expected_lines != actual_lines:
            raise DescriptionGenerationError(
                "Description line order does not match invoice line order"
            )

        for description in descriptions:
            if not description.description_en.strip() or not description.description_pl.strip():
                raise DescriptionGenerationError(
                    f"Description text is empty for line {description.line_no}"
                )
            for field_name in (
                "description_en",
                "description_pl",
                "made_of",
                "made_in",
                "country_of_origin",
                "melt_and_pour",
            ):
                value = getattr(description, field_name)
                if not value.strip():
                    raise DescriptionGenerationError(
                        f"{field_name} is empty for line {description.line_no}"
                    )
                if self._contains_banned_words(value):
                    raise DescriptionGenerationError(
                        f"{field_name} contains a banned material word for line {description.line_no}"
                    )

    def _build_openai_payload_item(self, item: InvoiceLineItem) -> dict[str, object]:
        return {
            "line_no": item.line_no,
            "item_name": item.item_name,
            "hs_code": item.hs_code,
            "invoice_origin_hint": item.origin,
            "currency": item.currency,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "line_value": item.line_value,
            "unit_net_weight_kg": item.unit_net_weight_kg,
            "total_net_weight_kg": item.total_net_weight_kg,
            "source_text": item.source_text,
        }

    def _build_description_entry(
        self,
        item: InvoiceLineItem,
        *,
        description_en: str,
        description_pl: str,
        made_of: str,
        made_in: str,
        country_of_origin: str,
        melt_and_pour: str,
        manufacturer_data: str,
    ) -> GoodsDescriptionEntry:
        return GoodsDescriptionEntry(
            line_no=item.line_no,
            item_name=item.item_name,
            hs_code=item.hs_code,
            description_en=description_en,
            description_pl=description_pl,
            made_of=made_of,
            made_in=made_in,
            country_of_origin=country_of_origin,
            melt_and_pour=melt_and_pour,
            manufacturer_data=manufacturer_data,
            currency=item.currency,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_value=item.line_value,
            net_weight_kg=item.total_net_weight_kg,
        )

    def _sanitize_for_matching(self, value: str) -> str:
        cleaned = value.lower()
        for banned_word in BANNED_WORDS:
            cleaned = re.sub(rf"\b{re.escape(banned_word)}\b", "", cleaned, flags=re.IGNORECASE)
        return collapse_whitespace(cleaned)

    def _sanitize_description(self, value: str) -> str:
        cleaned = self._strip_banned_words(value.strip())
        cleaned = re.sub(r"\bprofessional\b", "home", cleaned, flags=re.IGNORECASE)
        return collapse_whitespace(cleaned)

    def _contains_banned_words(self, value: str) -> bool:
        return any(
            re.search(rf"\b{re.escape(banned_word)}\b", value, flags=re.IGNORECASE)
            for banned_word in BANNED_WORDS
        )

    def _normalize_country(self, origin: str) -> str:
        if not origin or not origin.strip():
            return "N/A"
        cleaned = collapse_whitespace(origin.strip())
        normalized = cleaned.upper()
        if normalized in {"UNKNOWN", "N/A", "NA", "NOT APPLICABLE"}:
            return "UNKNOWN"
        return COUNTRY_MAP.get(normalized, cleaned)

    def _openai_country_fallback(self, origin: str) -> str:
        if not origin or not origin.strip():
            return "UNKNOWN"
        return self._normalize_country(origin)

    def _normalize_openai_country_field(self, value: str, fallback: str) -> str:
        cleaned = clean_optional_text(value)
        normalized = cleaned.strip().upper()
        if normalized in {"", "N/A", "NA", "NOT APPLICABLE", "UNKNOWN"}:
            cleaned = fallback
        if not cleaned or cleaned.strip().upper() in {"", "N/A", "NA", "NOT APPLICABLE"}:
            return "UNKNOWN"
        normalized_country = self._normalize_country(cleaned)
        return normalized_country if normalized_country != "N/A" else "UNKNOWN"

    def _infer_manufacturer(self, item_name: str) -> str:
        normalized = self._sanitize_for_matching(item_name)
        for keywords, manufacturer in MANUFACTURER_RULES:
            if any(keyword in normalized for keyword in keywords):
                return manufacturer
        return "UNKNOWN"

    def _normalize_material_field(self, value: Any) -> str:
        cleaned = clean_optional_text(value, fallback="UNKNOWN")
        if cleaned.strip().upper() in {"N/A", "NA", "NOT APPLICABLE"}:
            return "UNKNOWN"
        cleaned = collapse_whitespace(self._strip_banned_words(cleaned)) or "UNKNOWN"
        lowered = cleaned.lower()
        if lowered in {"", "unknown"}:
            return "UNKNOWN"

        metal_present = self._contains_any_word(lowered, self.METAL_HINTS)
        wood_present = self._contains_any_word(
            lowered,
            ("wood", "wooden", "timber", "bamboo", "plywood", "oak", "pine", "mahogany"),
        )
        non_metal_material = self._extract_primary_non_metal_material(lowered)
        generic_mix_markers = (
            "/",
            "&",
            " and ",
            " with ",
            " mixed ",
            " composite ",
            " blend",
            " part",
            " parts",
        )
        looks_mixed = any(marker in lowered for marker in generic_mix_markers)

        if metal_present and not non_metal_material and not wood_present and not looks_mixed:
            return "steel"
        if wood_present and not non_metal_material and not metal_present:
            return "composite"
        if metal_present or wood_present:
            return non_metal_material or "composite"
        return non_metal_material or "composite"

    def _derive_melt_and_pour(
        self,
        made_of: str,
        made_in: str,
        country_of_origin: str,
    ) -> str:
        normalized = collapse_whitespace(made_of).lower()
        if not normalized:
            return "N/A"
        if not any(hint in normalized for hint in self.METAL_HINTS):
            return "N/A"

        countries = [
            value.strip()
            for value in (made_in, country_of_origin)
            if value and value.strip() and value.strip().upper() not in {"UNKNOWN", "N/A"}
        ]
        if not countries:
            return "UNKNOWN"
        if len(countries) == 1 or countries[0] == countries[-1]:
            return countries[0]
        return " / ".join(dict.fromkeys(countries))

    def _normalize_manufacturer_data(
        self,
        value: Any,
    ) -> str:
        cleaned = self._sanitize_manufacturer_data(clean_optional_text(value))
        if cleaned.upper() in {"UNKNOWN", "N/A"}:
            return ""
        return cleaned

    def _strip_banned_words(self, value: str) -> str:
        cleaned = value
        for banned_word in BANNED_WORDS:
            cleaned = re.sub(rf"\b{re.escape(banned_word)}\b", "", cleaned, flags=re.IGNORECASE)
        return cleaned

    def _sanitize_manufacturer_data(self, value: str) -> str:
        cleaned = value.strip()
        cleaned = re.split(r"\s*\(\[", cleaned, maxsplit=1)[0]
        cleaned = collapse_whitespace(cleaned)
        return cleaned.strip(" ,;.")

    def _contains_any_word(self, value: str, words: tuple[str, ...]) -> bool:
        return any(
            re.search(rf"(?<![A-Za-z]){re.escape(word)}(?![A-Za-z])", value, flags=re.IGNORECASE)
            for word in words
        )

    def _extract_primary_non_metal_material(self, value: str) -> str:
        material_map = (
            (("plastic", "polymer", "pp", "pe", "pvc", "abs", "resin"), "plastic"),
            (("paper", "cardboard", "card", "kraft", "pulp"), "paper"),
            (("rubber", "latex", "silicone", "silicon"), "rubber"),
            (("textile", "fabric", "cotton", "polyester", "nylon", "felt", "wool"), "textile"),
            (("leather", "pu leather", "faux leather"), "leather"),
            (("glass",), "glass"),
            (("ceramic", "porcelain"), "ceramic"),
            (("stone", "marble", "granite"), "stone"),
        )
        for keywords, material in material_map:
            if self._contains_any_word(value, keywords):
                return material
        return ""
