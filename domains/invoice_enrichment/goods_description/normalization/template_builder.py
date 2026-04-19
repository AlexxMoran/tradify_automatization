from __future__ import annotations

import re

from core.utils import collapse_whitespace
from domains.invoice_enrichment.goods_description.rules import (
    ENGLISH_REQUIRED_SUFFIX,
    POLISH_REQUIRED_SUFFIXES,
)
from domains.invoice_enrichment.models import InvoiceLineItem


class TemplateBuilder:
    def build(
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
                return self._en(
                    f"Thule {core_name} accessory for bicycle wall mounting holder"
                )
            return self._pl(
                f"Akcesorium Thule {core_name} do sciennego uchwytu rowerowego",
                "neutral",
            )
        if category_key == "video_game":
            if language == "en":
                target = (
                    f"{item_name} video game for {platform} console"
                    if platform
                    else f"{item_name} video game"
                )
                return self._en(target)
            target = (
                f"Gra wideo {item_name} na konsole {platform}"
                if platform
                else f"Gra wideo {item_name}"
            )
            return self._pl(target, "feminine")
        if category_key == "vinyl_record":
            if language == "en":
                return self._en(f"{item_name} vinyl record for music playback")
            return self._pl(
                f"Plyta winylowa {item_name} do odtwarzania muzyki w uzytku domowym",
                "feminine",
            )
        if category_key == "blu_ray":
            if language == "en":
                return self._en(f"{item_name} Blu-ray disc for video playback")
            return self._pl(
                f"Plyta Blu-ray {item_name} do odtwarzania wideo w uzytku domowym",
                "feminine",
            )
        if category_key == "bicycle_tyre":
            if language == "en":
                return self._en(f"{item_name} bicycle tyre for {style_en} cycling")
            return self._pl(
                f"Opona rowerowa {item_name} do jazdy {style_pl}", "feminine"
            )
        if category_key == "bicycle_tube":
            if language == "en":
                valve_part = f" with {valve} valve" if valve else ""
                return self._en(f"{item_name} bicycle inner tube{valve_part}")
            valve_part = f" z zaworem {valve}" if valve else ""
            return self._pl(f"Detka rowerowa {item_name}{valve_part}", "feminine")
        if category_key == "valve_conversion":
            if language == "en":
                return self._en(
                    f"Bicycle valve conversion kit {item_name} for inflating bicycle tyres"
                )
            return self._pl(
                f"Zestaw do konwersji zaworu rowerowego {item_name}", "masculine"
            )
        if category_key == "puzzle":
            if language == "en":
                count_part = f" {puzzle_count}-piece" if puzzle_count else ""
                return self._en(f"{item_name}{count_part} jigsaw puzzle")
            count_part = f" {puzzle_count} elementow" if puzzle_count else ""
            return self._pl(f"Puzzle {item_name}{count_part}", "neutral")
        if category_key == "music_accessory":
            if language == "en":
                return self._en(f"{item_name} musical instrument accessory")
            return self._pl(
                f"Akcesorium do instrumentu muzycznego {item_name}", "neutral"
            )
        if category_key == "headphones":
            if language == "en":
                return self._en(f"{item_name} headphones for household audio use")
            return self._pl(
                f"Sluchawki {item_name} do domowego uzytku audio", "neutral"
            )
        if category_key == "textile":
            if language == "en":
                return self._en(f"{item_name} textile accessory for household use")
            return self._pl(f"Akcesorium tekstylne {item_name}", "neutral")
        if language == "en":
            return self._en(f"{item_name} household product for everyday use")
        return self._pl(
            f"Produkt {item_name} do codziennego uzytku domowego", "masculine"
        )

    def _en(self, text: str) -> str:
        return f"{text}, {ENGLISH_REQUIRED_SUFFIX}"

    def _pl(self, text: str, grammatical_kind: str) -> str:
        return f"{text}, {self._polish_suffix(grammatical_kind)}"

    def _polish_suffix(self, grammatical_kind: str) -> str:
        fallback_by_kind = {
            "masculine": "przeznaczony do uzytku domowego.",
            "feminine": "przeznaczona do uzytku domowego.",
            "neutral": "przeznaczone do uzytku domowego.",
        }
        index_by_kind = {"masculine": 0, "feminine": 1, "neutral": 2}
        index = index_by_kind.get(grammatical_kind, 0)
        if len(POLISH_REQUIRED_SUFFIXES) > index:
            return POLISH_REQUIRED_SUFFIXES[index]
        return fallback_by_kind.get(grammatical_kind, fallback_by_kind["masculine"])

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
