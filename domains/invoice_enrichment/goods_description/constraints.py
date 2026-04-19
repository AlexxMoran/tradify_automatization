from __future__ import annotations

from dataclasses import dataclass

from domains.invoice_enrichment.goods_description.rules import (
    AI_OWNED_FIELDS,
    ALLOWED_MATERIALS,
    BANNED_MATERIAL_COMBINATIONS,
    BANNED_WORDS,
    CODE_OWNED_FIELDS,
    ENGLISH_REQUIRED_SUFFIX,
    POLISH_REQUIRED_SUFFIXES,
    REVIEW_PATCH_ALLOWED_FIELDS,
    RULE_PREFERRED_FIELDS,
)


@dataclass(frozen=True, slots=True)
class FieldOwnership:
    ai_owned: tuple[str, ...]
    code_owned: tuple[str, ...]
    rule_preferred: tuple[str, ...]
    review_patch_allowed: tuple[str, ...]


FIELD_OWNERSHIP = FieldOwnership(
    ai_owned=AI_OWNED_FIELDS,
    code_owned=CODE_OWNED_FIELDS,
    rule_preferred=RULE_PREFERRED_FIELDS,
    review_patch_allowed=REVIEW_PATCH_ALLOWED_FIELDS,
)
REVIEW_PATCH_FIELDS = set(FIELD_OWNERSHIP.review_patch_allowed)


def allowed_materials_text() -> str:
    return ", ".join(ALLOWED_MATERIALS)


def banned_material_words_text() -> str:
    return ", ".join(sorted(BANNED_WORDS))


def banned_material_combinations_text() -> str:
    examples = [f"'{value.strip() or value}'" for value in BANNED_MATERIAL_COMBINATIONS]
    return ", ".join(examples)


def polish_suffixes_text() -> str:
    return ", ".join(f"'{suffix}'" for suffix in POLISH_REQUIRED_SUFFIXES)


def english_suffix_text() -> str:
    return ENGLISH_REQUIRED_SUFFIX
