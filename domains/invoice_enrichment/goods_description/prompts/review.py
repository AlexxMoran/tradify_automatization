from __future__ import annotations

import json

from domains.invoice_enrichment.goods_description.constraints import (
    FIELD_OWNERSHIP,
    allowed_materials_text,
    english_suffix_text,
    polish_suffixes_text,
)
from domains.invoice_enrichment.goods_description.rules import CHINA_ORIGIN_FALLBACK


def build_goods_description_review_prompt(
    payload: list[dict[str, object]],
    *,
    document_type: str,
    document_ref: str | None,
) -> str:
    return (
        "Review customs goods description drafts and return only corrections. "
        "You receive original invoice row data, local rule hints, the current draft, and validation issues. "
        "Check whether manufacturer_data belongs to the likely brand/manufacturer rather than a distributor, marketplace seller, or unrelated company. "
        "Check whether country_of_origin, made_in, material, and descriptions match the row and local hints. "
        "Return strict JSON in the form "
        '{"items":[{"line_no":1,"changes":[{"field":"manufacturer_data","value":"...","reason":"..."}]}]}. '
        "Only include fields that must change. "
        f"Allowed change fields are: {', '.join(FIELD_OWNERSHIP.review_patch_allowed)}. "
        "Do not include melt_and_pour; it is calculated by code. "
        "Never return empty strings, UNKNOWN, N/A, None, null, URLs, emails, social handles, usernames, or marketplace aliases. "
        "manufacturer_data must contain only the legal company name and postal address. "
        "If local strict fields exist, preserve them unless the row clearly proves they are impossible. "
        f"Descriptions must be household-safe. English descriptions must end with '{english_suffix_text()}'. "
        f"Polish descriptions must end with one of: {polish_suffixes_text()}. "
        f"made_of must be exactly one of: {allowed_materials_text()}. "
        "If invoice_origin_hint is CN, do not return China. "
        f"Use the brand country, or {CHINA_ORIGIN_FALLBACK} if the brand itself still resolves to China. "
        f"Document type: {document_type}. "
        f"Document ref: {document_ref or ''}. "
        f"Rows to review: {json.dumps(payload, ensure_ascii=False)}"
    )
