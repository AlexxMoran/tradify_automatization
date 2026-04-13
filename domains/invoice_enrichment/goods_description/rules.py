from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

BANNED_WORDS = {
    "aluminium",
    "aluminum",
    "copper",
    "wood",
    "brass",
}

ALLOWED_MATERIALS = (
    "Plastic",
    "Rubber",
    "Textile",
    "Composite",
    "Steel",
)

BANNED_MATERIAL_COMBINATIONS = (
    "/",
    "+",
    " and ",
    " with ",
)

COUNTRY_MAP = {
    "DE": "Germany",
    "AT": "Austria",
    "PL": "Poland",
    "CN": "China",
    "US": "United States",
    "USA": "United States",
    "GB": "United Kingdom",
    "UK": "United Kingdom",
    "IT": "Italy",
    "ES": "Spain",
    "FR": "France",
    "CZ": "Czech Republic",
    "NL": "Netherlands",
    "JP": "Japan",
    "SE": "Sweden",
    "DK": "Denmark",
    "IN": "India",
    "TW": "Taiwan",
}

PLACEHOLDER_VALUES = {"", "UNKNOWN", "N/A", "NA", "NOT APPLICABLE", "NONE", "NULL"}

THULE_FORBIDDEN_DESCRIPTION_TERMS = (
    "roof rack",
    "car",
    "automotive",
    "roof",
    "dachowy",
    "samochodowy",
)

ADDRESS_STREET_HINTS = (
    "street",
    "strasse",
    "str.",
    "road",
    "rd",
    "avenue",
    "ave",
    "blvd",
    "boulevard",
    "way",
    "close",
    "drive",
    "dr",
    "lane",
    "ln",
    "allee",
    "plein",
    "vej",
    "ul.",
    "ulitsa",
    "industrial estate",
    "business centre",
    "business center",
    "suite",
    "unit",
    "postbus",
)

ADDRESS_BANNED_ARTIFACTS = (
    "@",
    "http://",
    "https://",
    "www.",
    ".com",
    ".net",
    ".org",
    "instagram",
    "facebook",
    "tiktok",
    "youtube",
    "linkedin",
    "telegram",
    "whatsapp",
    "discord",
    "twitter",
    "x.com",
    "handle",
    "username",
    "user:",
    "ig:",
    "fb:",
)


@dataclass(frozen=True, slots=True)
class BrandRule:
    id: str
    keywords: tuple[str, ...]
    brand_name: str
    manufacturer_name: str
    country_of_origin: str
    manufacturer_data: str
    strict_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CategoryRule:
    id: str
    keywords: tuple[str, ...]
    material_override: str
    description_en_hint: str
    description_pl_hint: str
    strict_terms: tuple[str, ...]
    prompt_notes: tuple[str, ...]


def normalize_lookup_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _data_path(filename: str) -> Path:
    return Path(__file__).resolve().parents[1] / "data" / filename


@lru_cache()
def load_brand_rules() -> tuple[BrandRule, ...]:
    payload = json.loads(_data_path("brands.json").read_text(encoding="utf-8"))
    return tuple(
        BrandRule(
            id=str(item["id"]),
            keywords=tuple(str(value) for value in item.get("keywords", [])),
            brand_name=str(item.get("brand_name", "")),
            manufacturer_name=str(item.get("manufacturer_name", "")),
            country_of_origin=str(item.get("country_of_origin", "")),
            manufacturer_data=str(item.get("manufacturer_data", "")),
            strict_fields=tuple(str(value) for value in item.get("strict_fields", [])),
        )
        for item in payload
    )


@lru_cache()
def load_category_rules() -> tuple[CategoryRule, ...]:
    payload = json.loads(_data_path("categories.json").read_text(encoding="utf-8"))
    return tuple(
        CategoryRule(
            id=str(item["id"]),
            keywords=tuple(str(value) for value in item.get("keywords", [])),
            material_override=str(item.get("material_override", "")),
            description_en_hint=str(item.get("description_en_hint", "")),
            description_pl_hint=str(item.get("description_pl_hint", "")),
            strict_terms=tuple(str(value) for value in item.get("strict_terms", [])),
            prompt_notes=tuple(str(value) for value in item.get("prompt_notes", [])),
        )
        for item in payload
    )
