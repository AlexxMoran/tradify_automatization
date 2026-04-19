from __future__ import annotations

import json

from domains.invoice_enrichment.goods_description.constraints import (
    allowed_materials_text,
    banned_material_combinations_text,
    banned_material_words_text,
    english_suffix_text,
    polish_suffixes_text,
)
from domains.invoice_enrichment.goods_description.rules import CHINA_ORIGIN_FALLBACK


def build_goods_description_prompt(
    payload: list[dict[str, object]],
    *,
    document_type: str,
    document_ref: str | None,
) -> str:
    return (
        "You enrich invoice rows for a customs goods description table. "
        "Do not add or remove rows. "
        "Return strict JSON in the form "
        '{"items":[{"line_no":1,"description_en":"...","description_pl":"...",'
        '"made_of":"...","made_in":"...","country_of_origin":"...",'
        '"melt_and_pour":"...","manufacturer_data":"..."}]}. '
        "You always receive invoice row data plus optional local rule hints. "
        "Use local rule hints as a first-class signal. "
        "If a local hint is present in a strict field, preserve it unless it is clearly impossible. "
        "If the local hints are partial, complete the missing fields using inference and web search. "
        "If no local hint exists, infer everything from the row itself. "
        "Never return empty strings, UNKNOWN, N/A, None, null, or placeholder text for description_en, description_pl, made_of, made_in, country_of_origin, or manufacturer_data. "
        "Manufacturer's data MUST include a full postal-style legal address with company name, street, postal code, city, and country. "
        "Responses without a street-style address are not acceptable unless the official address itself uses a business centre or industrial estate format. "
        "Do not include URLs, website names, emails, social media handles, usernames, marketplace seller names, or contact nicknames in manufacturer_data. "
        "manufacturer_data must be only the legal entity name and its postal address. "
        "Treat invoice_origin_hint only as a weak fallback. "
        "Country of origin must be based on the real brand or manufacturer, not on invoice origin. "
        "If invoice_origin_hint is CN, never return China as the final country when a non-China brand country is available. "
        f"If the brand itself still resolves to China, return {CHINA_ORIGIN_FALLBACK} instead of China. "
        "Do not mention China in descriptions. "
        "Made in should follow country_of_origin unless a stronger brand-specific signal clearly indicates another valid country. "
        "If the product is fully metal, made_of may be 'Steel' and melt_and_pour must equal made_in. "
        "If the product is not fully metal, melt_and_pour must be 'N/A'. "
        "Descriptions must be household-safe and must end with the exact endings: "
        f"PL descriptions end with one of: {polish_suffixes_text()}. "
        f"EN descriptions end with '{english_suffix_text()}'. "
        "If the local category hint mentions wording constraints, obey them exactly. "
        "Avoid dangerous, weapon-like, or alarming wording. Soften risky goods into household-safe wording when possible. "
        f"Do not use banned material words in made_of: {banned_material_words_text()}. "
        f"Do not use composite material strings with markers such as {banned_material_combinations_text()}. "
        f"The made_of field must be exactly one of: {allowed_materials_text()}. "
        "Choose the simplest safe material from that allowed list. "
        f"Document type: {document_type}. "
        f"Document ref: {document_ref or ''}. "
        f"Invoice items: {json.dumps(payload, ensure_ascii=False)}"
    )
