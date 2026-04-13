from __future__ import annotations

import re
from typing import Any

from core.utils import clean_optional_text, collapse_whitespace
from domains.invoice_enrichment.goods_description.dto import GoodsDescriptionDraft
from domains.invoice_enrichment.goods_description.rules import (
    ADDRESS_BANNED_ARTIFACTS,
    ADDRESS_STREET_HINTS,
    ALLOWED_MATERIALS,
    BANNED_MATERIAL_COMBINATIONS,
    BANNED_WORDS,
    COUNTRY_MAP,
    PLACEHOLDER_VALUES,
    THULE_FORBIDDEN_DESCRIPTION_TERMS,
)
from domains.invoice_enrichment.models import (
    GoodsDescriptionEntry,
    InvoiceLineItem,
    ResolvedRuleHints,
)


class GoodsDescriptionNormalizer:
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

    def merge_descriptions(
        self,
        line_items: list[InvoiceLineItem],
        hints_by_line: dict[int, ResolvedRuleHints],
        raw_items: list[GoodsDescriptionDraft],
        *,
        repaired_by_line: dict[int, GoodsDescriptionDraft] | None = None,
    ) -> list[GoodsDescriptionEntry]:
        raw_by_line = {item.line_no: item for item in raw_items}
        repaired_by_line = repaired_by_line or {}

        descriptions: list[GoodsDescriptionEntry] = []
        for source_item in line_items:
            hints = hints_by_line[source_item.line_no]
            base_entry = raw_by_line.get(source_item.line_no)
            repaired_entry = repaired_by_line.get(source_item.line_no)
            entry = self.merge_openai_entry(
                source_item, hints, base_entry, repaired_entry
            )
            descriptions.append(entry)
        return descriptions

    def merge_openai_entry(
        self,
        item: InvoiceLineItem,
        hints: ResolvedRuleHints,
        base_entry: GoodsDescriptionDraft | None,
        repaired_entry: GoodsDescriptionDraft | None,
    ) -> GoodsDescriptionEntry:
        raw_entry = self._merge_drafts(base_entry, repaired_entry)
        country_fallback = self._country_fallback(item.origin, hints)
        country_of_origin = self._resolve_country_field(
            raw_entry.country_of_origin,
            hint=hints.country_of_origin_hint,
            invoice_origin=item.origin,
        )
        made_in = self._resolve_country_field(
            raw_entry.made_in,
            hint=hints.made_in_hint or country_of_origin,
            invoice_origin=item.origin,
        )
        if "made_in" in hints.strict_fields or not made_in:
            made_in = country_of_origin

        made_of = self._resolve_material_field(
            raw_entry.made_of,
            hint=hints.made_of_hint,
            item=item,
        )
        manufacturer_data = self._resolve_manufacturer_data(
            raw_entry.manufacturer_data,
            hint=hints.manufacturer_data_hint,
            invoice_origin=item.origin,
            country_of_origin=country_of_origin,
        )
        description_en = self._resolve_description(
            raw_entry.description_en,
            hint=hints.description_en_hint,
            language="en",
            category_key=hints.category_key,
            item=item,
        )
        description_pl = self._resolve_description(
            raw_entry.description_pl,
            hint=hints.description_pl_hint,
            language="pl",
            category_key=hints.category_key,
            item=item,
        )

        if "country_of_origin" in hints.strict_fields and hints.country_of_origin_hint:
            country_of_origin = hints.country_of_origin_hint
        if "made_in" in hints.strict_fields and hints.made_in_hint:
            made_in = hints.made_in_hint
        if "manufacturer_data" in hints.strict_fields and hints.manufacturer_data_hint:
            manufacturer_data = hints.manufacturer_data_hint

        if not country_of_origin:
            country_of_origin = country_fallback
        if not made_in:
            made_in = country_of_origin

        manufacturer_data = manufacturer_data or hints.manufacturer_data_hint
        made_of = made_of or hints.made_of_hint or self.fallback_material(item)
        description_en = description_en or hints.description_en_hint
        description_pl = description_pl or hints.description_pl_hint
        melt_and_pour = self.derive_melt_and_pour(item, made_of, made_in)

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

    def build_openai_payload_item(
        self,
        item: InvoiceLineItem,
        hints: ResolvedRuleHints,
    ) -> dict[str, object]:
        return {
            "line_no": item.line_no,
            "item_name": item.item_name,
            "hs_code": item.hs_code,
            "invoice_origin_hint": item.origin or "",
            "currency": item.currency,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "line_value": item.line_value,
            "unit_net_weight_kg": item.unit_net_weight_kg,
            "total_net_weight_kg": item.total_net_weight_kg,
            "source_text": item.source_text,
            "resolved_hints": hints.to_prompt_dict(),
        }

    def expected_melt_and_pour(
        self, item: InvoiceLineItem, made_of: str, made_in: str
    ) -> str:
        if self.is_fully_metal_material(made_of) or self.looks_fully_metal(
            collapse_whitespace(f"{item.item_name} {item.source_text}").lower()
        ):
            return made_in
        return "N/A"

    def is_placeholder(self, value: str | None) -> bool:
        if value is None:
            return True
        return collapse_whitespace(str(value)).upper() in PLACEHOLDER_VALUES

    def material_contains_banned_words(self, value: str) -> bool:
        lowered = value.lower()
        if any(word in lowered.split() for word in BANNED_WORDS):
            return True
        if any(marker in lowered for marker in BANNED_MATERIAL_COMBINATIONS):
            return True
        return value not in ALLOWED_MATERIALS

    def is_full_address(self, value: str) -> bool:
        cleaned = self._sanitize_manufacturer_data(value)
        if self.is_placeholder(cleaned):
            return False
        if self._contains_address_artifacts(cleaned):
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

    def has_valid_polish_suffix(self, value: str) -> bool:
        lowered = value.lower()
        return (
            lowered.endswith("przeznaczony do uzytku domowego.")
            or lowered.endswith("przeznaczona do uzytku domowego.")
            or lowered.endswith("przeznaczone do uzytku domowego.")
        )

    def address_mentions_china(self, value: str) -> bool:
        lowered = self._sanitize_manufacturer_data(value).lower()
        return " china" in f" {lowered}" or lowered.endswith("china")

    def derive_melt_and_pour(
        self, item: InvoiceLineItem, made_of: str, made_in: str
    ) -> str:
        if self.is_fully_metal_material(made_of) or self.looks_fully_metal(
            collapse_whitespace(f"{item.item_name} {item.source_text}").lower()
        ):
            return made_in
        return "N/A"

    def fallback_material(self, item: InvoiceLineItem) -> str:
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

    def _merge_drafts(
        self,
        base_entry: GoodsDescriptionDraft | None,
        repaired_entry: GoodsDescriptionDraft | None,
    ) -> GoodsDescriptionDraft:
        merged = GoodsDescriptionDraft(
            line_no=(
                repaired_entry or base_entry or GoodsDescriptionDraft(line_no=0)
            ).line_no
        )
        for field_name in (
            "description_en",
            "description_pl",
            "made_of",
            "made_in",
            "country_of_origin",
            "melt_and_pour",
            "manufacturer_data",
        ):
            base_value = getattr(base_entry, field_name, "")
            repaired_value = getattr(repaired_entry, field_name, "")
            setattr(merged, field_name, repaired_value or base_value)
        return merged

    def _resolve_country_field(
        self, value: Any, *, hint: str, invoice_origin: str | None
    ) -> str:
        raw = clean_optional_text(value)
        if self.is_placeholder(raw):
            raw = hint
        if self.is_placeholder(raw):
            raw = self._country_fallback(invoice_origin, None)
        raw = clean_optional_text(raw)
        normalized = COUNTRY_MAP.get(raw.upper(), raw)
        if normalized == "China" and (
            clean_optional_text(invoice_origin).upper() == "CN"
            or (hint and hint != "China")
        ):
            if hint and hint != "China":
                normalized = hint
            else:
                normalized = "Taiwan"
        return collapse_whitespace(normalized)

    def _country_fallback(
        self, invoice_origin: str | None, hints: ResolvedRuleHints | None
    ) -> str:
        if hints and hints.country_of_origin_hint:
            return hints.country_of_origin_hint
        if not invoice_origin:
            return ""
        normalized = collapse_whitespace(invoice_origin).upper()
        mapped = COUNTRY_MAP.get(normalized, collapse_whitespace(invoice_origin))
        if mapped == "China":
            return "Taiwan"
        return mapped

    def _resolve_material_field(
        self, value: Any, *, hint: str, item: InvoiceLineItem
    ) -> str:
        raw = clean_optional_text(value)
        if self.is_placeholder(raw):
            raw = hint
        raw = self._normalize_material(raw)
        if self.looks_fully_metal(
            collapse_whitespace(f"{item.item_name} {item.source_text}").lower()
        ):
            return "Steel"
        if raw:
            return raw
        hint_material = self._normalize_material(hint)
        if hint_material:
            return hint_material
        return self.fallback_material(item)

    def _resolve_manufacturer_data(
        self,
        value: Any,
        *,
        hint: str,
        invoice_origin: str | None,
        country_of_origin: str,
    ) -> str:
        raw = self._sanitize_manufacturer_data(clean_optional_text(value))
        if self._is_acceptable_address(
            raw, invoice_origin=invoice_origin, country_of_origin=country_of_origin
        ):
            return raw
        hint = self._sanitize_manufacturer_data(hint)
        if self._is_acceptable_address(
            hint, invoice_origin=invoice_origin, country_of_origin=country_of_origin
        ):
            return hint
        return raw or hint

    def _resolve_description(
        self,
        value: Any,
        *,
        hint: str,
        language: str,
        category_key: str,
        item: InvoiceLineItem,
    ) -> str:
        raw = clean_optional_text(value)
        if self.is_placeholder(raw):
            raw = hint
        raw = self._sanitize_description(
            raw, language=language, category_key=category_key
        )
        if raw:
            if category_key == "thule_bicycle_mount":
                return self._build_category_fallback_description(
                    item,
                    language=language,
                    category_key=category_key,
                )
            return raw
        return self._build_category_fallback_description(
            item,
            language=language,
            category_key=category_key,
        )

    def _sanitize_description(
        self, value: str, *, language: str, category_key: str
    ) -> str:
        cleaned = collapse_whitespace(value.strip())
        cleaned = re.sub(r"\bprofessional\b", "household", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(
            r"\bhome use use\b", "household use", cleaned, flags=re.IGNORECASE
        )
        if category_key == "thule_bicycle_mount":
            for term in THULE_FORBIDDEN_DESCRIPTION_TERMS:
                cleaned = re.sub(
                    re.escape(term),
                    "bicycle wall mounting",
                    cleaned,
                    flags=re.IGNORECASE,
                )

        if language == "en":
            if cleaned.lower().endswith("intended for household use."):
                return collapse_whitespace(cleaned)
            cleaned = re.sub(
                r"(,?\s*)?intended for household use\.?$",
                "",
                cleaned,
                flags=re.IGNORECASE,
            ).strip(" ,.;")
            cleaned = (
                f"{cleaned}, intended for household use."
                if cleaned
                else "Product intended for household use."
            )
            return collapse_whitespace(cleaned)

        if self.has_valid_polish_suffix(cleaned):
            return collapse_whitespace(cleaned)
        cleaned = re.sub(
            r"(,?\s*)?przeznaczon(?:y|a|e)\s+do\s+uzytku\s+domowego\.?$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip(" ,.;")
        suffix = self._guess_polish_suffix(cleaned)
        cleaned = f"{cleaned}, {suffix}" if cleaned else f"Produkt, {suffix}"
        return collapse_whitespace(cleaned)

    def _guess_polish_suffix(self, text: str) -> str:
        lowered = text.lower()
        if any(
            token in lowered
            for token in (
                "puzzle",
                "sluchawki",
                "druty",
                "gry",
                "akcesoria",
                "akcesorium",
            )
        ):
            return "przeznaczone do uzytku domowego."
        if any(
            token in lowered for token in ("opona", "detka", "gra", "plyta", "zabawka")
        ):
            return "przeznaczona do uzytku domowego."
        return "przeznaczony do uzytku domowego."

    def _normalize_material(self, value: str) -> str:
        cleaned = clean_optional_text(value)
        if self.is_placeholder(cleaned):
            return ""
        cleaned = re.sub(r"[(){}\[\]]", " ", cleaned)
        cleaned = cleaned.replace("&", " and ")
        if any(marker in cleaned.lower() for marker in BANNED_MATERIAL_COMBINATIONS):
            return ""
        return self._normalize_material_token(cleaned)

    def _normalize_material_token(self, value: str) -> str:
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

    def is_fully_metal_material(self, value: str) -> bool:
        return collapse_whitespace(value) == "Steel"

    def looks_fully_metal(self, text: str) -> bool:
        normalized = collapse_whitespace(text).lower()
        if not normalized:
            return False
        if not any(hint in normalized for hint in self.METAL_HINTS):
            return False
        return not any(hint in normalized for hint in self.NON_METAL_HINTS)

    def _sanitize_manufacturer_data(self, value: str) -> str:
        cleaned = value.strip()
        cleaned = re.split(r"\s*\(\[", cleaned, maxsplit=1)[0]
        cleaned = collapse_whitespace(cleaned)
        return cleaned.strip(" ,;.")

    def _contains_address_artifacts(self, value: str) -> bool:
        lowered = self._sanitize_manufacturer_data(value).lower()
        if not lowered:
            return False
        if any(token in lowered for token in ADDRESS_BANNED_ARTIFACTS):
            return True
        if re.search(r"\b\S+@\S+\b", lowered):
            return True
        if re.search(r"\b[a-z0-9._-]+@[a-z0-9._-]+\b", lowered):
            return True
        return False

    def _is_acceptable_address(
        self,
        value: str,
        *,
        invoice_origin: str | None,
        country_of_origin: str,
    ) -> bool:
        if not self.is_full_address(value):
            return False
        if self.address_mentions_china(value) and (
            clean_optional_text(invoice_origin).upper() == "CN"
            or country_of_origin != "China"
        ):
            return False
        return True

    def _build_category_fallback_description(
        self,
        item: InvoiceLineItem,
        *,
        language: str,
        category_key: str,
    ) -> str:
        item_name = collapse_whitespace(item.item_name)
        platform = self._extract_platform(item_name)
        valve = self._extract_valve_type(item_name)
        puzzle_count = self._extract_puzzle_count(item_name)
        style_en, style_pl = self._extract_bicycle_style(item_name)
        core_name = self._strip_brand_prefix(item_name, "Thule")

        if category_key == "thule_bicycle_mount":
            if language == "en":
                return f"Thule {core_name} accessory for bicycle wall mounting holder, intended for household use."
            return f"Akcesorium Thule {core_name} do sciennego uchwytu rowerowego, przeznaczone do uzytku domowego."
        if category_key == "video_game":
            if language == "en":
                target = (
                    f"{item_name} video game for {platform} console"
                    if platform
                    else f"{item_name} video game"
                )
                return f"{target}, intended for household use."
            target = (
                f"Gra wideo {item_name} na konsole {platform}"
                if platform
                else f"Gra wideo {item_name}"
            )
            return f"{target}, przeznaczona do uzytku domowego."
        if category_key == "vinyl_record":
            if language == "en":
                return f"{item_name} vinyl record for music playback, intended for household use."
            return f"Plyta winylowa {item_name} do odtwarzania muzyki w uzytku domowym, przeznaczona do uzytku domowego."
        if category_key == "blu_ray":
            if language == "en":
                return f"{item_name} Blu-ray disc for video playback, intended for household use."
            return f"Plyta Blu-ray {item_name} do odtwarzania wideo w uzytku domowym, przeznaczona do uzytku domowego."
        if category_key == "bicycle_tyre":
            if language == "en":
                return f"{item_name} bicycle tyre for {style_en} cycling, intended for household use."
            return f"Opona rowerowa {item_name} do jazdy {style_pl}, przeznaczona do uzytku domowego."
        if category_key == "bicycle_tube":
            if language == "en":
                valve_part = f" with {valve} valve" if valve else ""
                return f"{item_name} bicycle inner tube{valve_part}, intended for household use."
            valve_part = f" z zaworem {valve}" if valve else ""
            return f"Detka rowerowa {item_name}{valve_part}, przeznaczona do uzytku domowego."
        if category_key == "valve_conversion":
            if language == "en":
                return f"Bicycle valve conversion kit {item_name} for inflating bicycle tyres, intended for household use."
            return f"Zestaw do konwersji zaworu rowerowego {item_name}, przeznaczony do uzytku domowego."
        if category_key == "puzzle":
            if language == "en":
                count_part = f" {puzzle_count}-piece" if puzzle_count else ""
                return f"{item_name}{count_part} jigsaw puzzle, intended for household use."
            count_part = f" {puzzle_count} elementow" if puzzle_count else ""
            return f"Puzzle {item_name}{count_part}, przeznaczone do uzytku domowego."
        if category_key == "music_accessory":
            if language == "en":
                return f"{item_name} musical instrument accessory, intended for household use."
            return f"Akcesorium do instrumentu muzycznego {item_name}, przeznaczone do uzytku domowego."
        if category_key == "headphones":
            if language == "en":
                return f"{item_name} headphones for household audio use, intended for household use."
            return f"Sluchawki {item_name} do domowego uzytku audio, przeznaczone do uzytku domowego."
        if category_key == "textile":
            if language == "en":
                return f"{item_name} textile accessory for household use, intended for household use."
            return f"Akcesorium tekstylne {item_name}, przeznaczone do uzytku domowego."
        if language == "en":
            return f"{item_name} household product for everyday use, intended for household use."
        return f"Produkt {item_name} do codziennego uzytku domowego, przeznaczony do uzytku domowego."

    def _extract_platform(self, value: str) -> str:
        lowered = value.lower()
        for platform in (
            "PS5",
            "PS4",
            "Xbox Series X",
            "Xbox One",
            "Nintendo Switch",
            "PC",
        ):
            if platform.lower() in lowered:
                return platform
        return ""

    def _extract_valve_type(self, value: str) -> str:
        lowered = value.lower()
        for valve in ("Presta", "Dunlop", "Schrader"):
            if valve.lower() in lowered:
                return valve
        return ""

    def _extract_puzzle_count(self, value: str) -> str:
        match = re.search(
            r"\b(\d{2,5})\s*(?:pcs|pieces|elementow|elements?)\b",
            value,
            flags=re.IGNORECASE,
        )
        return match.group(1) if match else ""

    def _extract_bicycle_style(self, value: str) -> tuple[str, str]:
        lowered = value.lower()
        if any(token in lowered for token in ("urban", "city", "commute", "tour")):
            return "urban", "miejskiej"
        if any(
            token in lowered
            for token in ("mtb", "trail", "mud", "terrain", "gravel", "off-road", "xc")
        ):
            return "off-road", "terenowej"
        return "performance", "wyczynowej"

    def _strip_brand_prefix(self, value: str, brand: str) -> str:
        stripped = re.sub(
            rf"^\s*{re.escape(brand)}\s*", "", value, flags=re.IGNORECASE
        ).strip()
        return stripped or value
