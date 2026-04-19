from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


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
def load_customs_rules() -> dict[str, object]:
    return json.loads(_data_path("customs_rules.json").read_text(encoding="utf-8"))


def _customs_section(name: str) -> dict[str, object]:
    section = load_customs_rules().get(name, {})
    return section if isinstance(section, dict) else {}


def _customs_list(section_name: str, field_name: str) -> tuple[str, ...]:
    section = _customs_section(section_name)
    values = section.get(field_name, ())
    if not isinstance(values, list):
        return ()
    return tuple(str(value) for value in values)


def _customs_map(section_name: str, field_name: str) -> dict[str, str]:
    section = _customs_section(section_name)
    values = section.get(field_name, {})
    if not isinstance(values, dict):
        return {}
    return {str(key): str(value) for key, value in values.items()}


_COUNTRY_RULES = _customs_section("countries")
_DESCRIPTION_RULES = _customs_section("descriptions")
_FIELD_OWNERSHIP_RULES = _customs_section("field_ownership")

BANNED_WORDS = set(_customs_list("materials", "banned_words"))
ALLOWED_MATERIALS = _customs_list("materials", "allowed")
BANNED_MATERIAL_COMBINATIONS = _customs_list("materials", "banned_combinations")
COUNTRY_MAP = _customs_map("countries", "code_map")
CHINA_ORIGIN_FALLBACK = str(_COUNTRY_RULES.get("china_origin_fallback", "Taiwan"))
DEFAULT_UNKNOWN_COUNTRY = str(_COUNTRY_RULES.get("default_unknown_country", "Poland"))
PLACEHOLDER_VALUES = set(
    str(value) for value in load_customs_rules().get("placeholders", [])
)
ADDRESS_STREET_HINTS = _customs_list("address", "street_hints")
ADDRESS_BANNED_ARTIFACTS = _customs_list("address", "banned_artifacts")
ENGLISH_REQUIRED_SUFFIX = str(
    _DESCRIPTION_RULES.get("english_required_suffix", "intended for household use.")
)
POLISH_REQUIRED_SUFFIXES = _customs_list("descriptions", "polish_required_suffixes")
THULE_FORBIDDEN_DESCRIPTION_TERMS = _customs_list(
    "descriptions", "thule_forbidden_terms"
)
AI_OWNED_FIELDS = tuple(
    str(value) for value in _FIELD_OWNERSHIP_RULES.get("ai_owned", [])
)
CODE_OWNED_FIELDS = tuple(
    str(value) for value in _FIELD_OWNERSHIP_RULES.get("code_owned", [])
)
RULE_PREFERRED_FIELDS = tuple(
    str(value) for value in _FIELD_OWNERSHIP_RULES.get("rule_preferred", [])
)
REVIEW_PATCH_ALLOWED_FIELDS = tuple(
    str(value) for value in _FIELD_OWNERSHIP_RULES.get("review_patch_allowed", [])
)


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
