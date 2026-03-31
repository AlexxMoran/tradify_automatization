from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

from rules.goods_description_prompt import build_goods_description_prompt
from rules.goods_description_rules import (
    BANNED_WORDS,
    COUNTRY_MAP,
    DESCRIPTION_RULES,
    MANUFACTURER_RULES,
    MATERIAL_RULES,
)
from core.config import get_settings
from core.utils import clean_optional_text, collapse_whitespace
from models import GoodsDescriptionEntry, InvoiceLineItem


class DescriptionGenerationError(Exception):
    pass


class GoodsDescriptionGenerator:
    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = settings.openai_api_key
        self.model = settings.openai_model
        self.mode = settings.description_generation_mode.lower().strip() or "template"
        self._openai_client = None
        if self.api_key:
            from openai import AsyncOpenAI
            self._openai_client = AsyncOpenAI(api_key=self.api_key)

    async def generate(
        self,
        line_items: list[InvoiceLineItem],
    ) -> list[GoodsDescriptionEntry]:
        if self.mode == "openai" and not self.api_key:
            raise DescriptionGenerationError("OPENAI_API_KEY is required when DESCRIPTION_GENERATION_MODE=openai")

        if self.mode in {"openai", "hybrid"} and self._openai_client:
            try:
                descriptions = await self._generate_with_openai(line_items)
                self._validate_descriptions(line_items, descriptions)
                return descriptions
            except Exception as exc:
                if self.mode == "openai":
                    raise DescriptionGenerationError(
                        f"OpenAI description generation failed: {exc}"
                    ) from exc
                logger.warning("OpenAI generation failed, falling back to templates: %s", exc)

        descriptions = self._generate_with_templates(line_items)
        self._validate_descriptions(line_items, descriptions)
        return descriptions

    def _generate_with_templates(
        self,
        line_items: list[InvoiceLineItem],
    ) -> list[GoodsDescriptionEntry]:
        descriptions: list[GoodsDescriptionEntry] = []
        for item in line_items:
            description_en, description_pl = self._classify_description(item.item_name)
            country = self._normalize_country(item.origin)
            descriptions.append(
                self._build_description_entry(
                    item,
                    description_en=description_en,
                    description_pl=description_pl,
                    made_of=self._infer_material(item.item_name),
                    made_in=country,
                    country_of_origin=country,
                    melt_and_pour="N/A",
                    manufacturer_data=self._infer_manufacturer(item.item_name, country),
                )
            )
        return descriptions

    async def _generate_with_openai(
        self,
        line_items: list[InvoiceLineItem],
    ) -> list[GoodsDescriptionEntry]:
        payload = [self._build_openai_payload_item(item) for item in line_items]

        response = await self._openai_client.responses.create(
            model=self.model,
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
            descriptions.append(
                self._build_description_entry(
                    source_item,
                    description_en=self._sanitize_description(str(entry["description_en"])),
                    description_pl=self._sanitize_description(str(entry["description_pl"])),
                    made_of=self._normalize_material_field(entry.get("made_of")),
                    made_in=self._normalize_openai_country_field(made_in, country_fallback),
                    country_of_origin=self._normalize_openai_country_field(
                        country_of_origin,
                        country_fallback,
                    ),
                    melt_and_pour=clean_optional_text(entry.get("melt_and_pour"), fallback="N/A"),
                    manufacturer_data=clean_optional_text(
                        entry.get("manufacturer_data"),
                        fallback=self._infer_manufacturer(source_item.item_name, country_of_origin),
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
            if self._contains_banned_words(description.description_en):
                raise DescriptionGenerationError(
                    f"English description contains a banned material word for line {description.line_no}"
                )
            if self._contains_banned_words(description.description_pl):
                raise DescriptionGenerationError(
                    f"Polish description contains a banned material word for line {description.line_no}"
                )
            if self._contains_banned_words(description.made_of):
                raise DescriptionGenerationError(
                    f"made_of contains a banned material word for line {description.line_no}"
                )
            for field_name in (
                "made_of",
                "made_in",
                "country_of_origin",
                "melt_and_pour",
                "manufacturer_data",
            ):
                if not getattr(description, field_name).strip():
                    raise DescriptionGenerationError(
                        f"{field_name} is empty for line {description.line_no}"
                    )

    def _classify_description(self, item_name: str) -> tuple[str, str]:
        normalized = self._sanitize_for_matching(item_name)
        for keywords, labels in DESCRIPTION_RULES:
            if any(keyword in normalized for keyword in keywords):
                return labels
        return (
            "Household accessory intended for everyday use.",
            "Akcesorium domowe przeznaczone do codziennego uzytku.",
        )

    def _build_openai_payload_item(self, item: InvoiceLineItem) -> dict[str, object]:
        return {
            "line_no": item.line_no,
            "item_name": item.item_name,
            "hs_code": item.hs_code,
            "origin": item.origin,
            "currency": item.currency,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "line_value": item.line_value,
            "unit_net_weight_kg": item.unit_net_weight_kg,
            "total_net_weight_kg": item.total_net_weight_kg,
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
        cleaned = value.strip()
        for banned_word in BANNED_WORDS:
            cleaned = re.sub(rf"\b{re.escape(banned_word)}\b", "", cleaned, flags=re.IGNORECASE)
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
        normalized = origin.strip().upper()
        return COUNTRY_MAP.get(normalized, origin.strip())

    def _openai_country_fallback(self, origin: str) -> str:
        if not origin or not origin.strip():
            return "UNKNOWN"
        return self._normalize_country(origin)

    def _normalize_openai_country_field(self, value: str, fallback: str) -> str:
        cleaned = clean_optional_text(value, fallback=fallback)
        if cleaned.strip().upper() in {"N/A", "NA", "NOT APPLICABLE"}:
            return "UNKNOWN"
        return cleaned

    def _infer_material(self, item_name: str) -> str:
        normalized = self._sanitize_for_matching(item_name)
        for keywords, material in MATERIAL_RULES:
            if any(keyword in normalized for keyword in keywords):
                return material
        return "UNKNOWN"

    def _infer_manufacturer(self, item_name: str, country: str) -> str:
        normalized = self._sanitize_for_matching(item_name)
        for keywords, manufacturer in MANUFACTURER_RULES:
            if any(keyword in normalized for keyword in keywords):
                return manufacturer
        if country in {"UNKNOWN", "N/A"}:
            return "UNKNOWN"
        return f"UNKNOWN manufacturer, {country}"

    def _normalize_material_field(self, value: Any) -> str:
        cleaned = clean_optional_text(value, fallback="UNKNOWN")
        if cleaned.strip().upper() in {"N/A", "NA", "NOT APPLICABLE"}:
            return "UNKNOWN"
        for banned_word in BANNED_WORDS:
            cleaned = re.sub(rf"\b{re.escape(banned_word)}\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = collapse_whitespace(cleaned) or "UNKNOWN"
        lowered = cleaned.lower()

        if "plastic" in lowered and "steel" in lowered:
            return "Plastic/steel"

        slash_parts = [
            part.strip()
            for part in re.split(r"\s*/\s*|\s*&\s*|\s+and\s+", cleaned, flags=re.IGNORECASE)
            if part.strip()
        ]
        if len(slash_parts) >= 2:
            return f"{self._capitalize_material_word(slash_parts[0])}/{self._capitalize_material_word(slash_parts[1])}"

        words = [
            word
            for word in re.findall(r"[A-Za-z]+", cleaned)
            if word.lower() not in {"made", "of", "with", "from", "and"}
        ]
        if len(words) >= 2:
            return f"{self._capitalize_material_word(words[0])}/{self._capitalize_material_word(words[1])}"
        if len(words) == 1:
            return self._capitalize_material_word(words[0])
        return cleaned

    def _capitalize_material_word(self, value: str) -> str:
        lowered = value.strip().lower()
        if not lowered:
            return "Unknown"
        return lowered[0].upper() + lowered[1:]
